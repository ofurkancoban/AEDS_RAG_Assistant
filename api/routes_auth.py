import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from api.auth import (
    GUEST_EMAIL,
    create_access_token,
    create_guest_user,
    get_current_user_or_guest,
    hash_password,
    verify_password,
)
from api.rate_limit import auth_limiter, client_ip, guest_limiter
from config import settings
from db.models import Role, User, get_session

router = APIRouter(prefix="/auth", tags=["auth"])

# Enforced here rather than by a field validator so the error can say what is
# actually wrong. Previously there was no minimum at all - an empty password
# was accepted, and since verify_password("", hash_of_"") succeeds, that made
# the account trivially accessible to anyone who knew the address.
MIN_PASSWORD_LENGTH = 8

# Guests are never asked to log in again, so their token has to outlive a
# normal session or they silently lose their conversation history.
GUEST_TOKEN_MINUTES = 60 * 24 * 90

# bcrypt's own verify is deliberately slow (~100-300ms) - real protection
# against offline guessing, but a timing side channel on this endpoint: for
# an unknown email, `user` is None and short-circuit evaluation skips
# verify_password entirely, so that request returns in under a millisecond
# while a wrong-password guess against a REAL email takes the full bcrypt
# time. Both branches already return the identical error message so the
# response body cannot be used to enumerate accounts - but the response
# TIME still could, measurably, even over a network. Hashed once at import
# so every "no such user" login still burns a real bcrypt verify against
# this fixed hash, closing the timing gap without slowing down real logins.
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def _normalise_email(email: str) -> str:
    """Emails are case-insensitive in practice, so "A@x.com" and "a@x.com" are
    the same person. Without this they became two separate accounts, and
    logging in with different capitalisation than at registration just
    failed with "invalid credentials"."""
    return email.strip().lower()


def _enforce_auth_limit(request: Request) -> None:
    """Credential endpoints are the one place an attacker gets unlimited
    guesses at other people's accounts, so they are throttled by source IP
    independently of the chat limits."""
    key = f"auth:{client_ip(request)}"
    if not auth_limiter.check_and_record(key):
        raise HTTPException(
            status_code=429,
            detail="Too many attempts - please wait before trying again.",
            headers={"Retry-After": str(auth_limiter.retry_after(key))},
        )


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    email: str
    role: str
    is_guest: bool


@router.post("/guest", response_model=TokenResponse)
def create_guest_session(request: Request, session: Session = Depends(get_session)):
    """Issue a fresh anonymous identity so a visitor can use the assistant
    without registering and still be isolated from every other visitor.

    The client stores this token and reuses it; calling the endpoint again
    mints a *new* identity and abandons the previous one's history, so it is
    meant to be called once per browser rather than once per page load.
    """
    key = f"guest:{client_ip(request)}"
    if not guest_limiter.check_and_record(key):
        # Each call inserts a users row, so an unthrottled client could fill
        # the table just by looping this endpoint.
        raise HTTPException(
            status_code=429,
            detail="Too many guest sessions created - please wait before trying again.",
            headers={"Retry-After": str(guest_limiter.retry_after(key))},
        )

    guest = create_guest_user(session)
    return TokenResponse(
        access_token=create_access_token(guest, expires_minutes=GUEST_TOKEN_MINUTES)
    )


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user_or_guest)):
    """Lets the client show which identity it is acting as without decoding
    the JWT itself, and tells it when a stored token has stopped being valid
    so it can recover instead of failing every later call."""
    return MeResponse(
        id=user.id, email=user.email, role=user.role.value, is_guest=bool(user.is_guest)
    )


@router.post("/register", response_model=TokenResponse)
def register(request: Request, payload: RegisterRequest, session: Session = Depends(get_session)):
    """Bootstrap only: creates the first admin, then closes permanently.

    Students are not meant to have accounts at all - everyone using the
    assistant stays anonymous, identified by a per-session guest identity (see
    /auth/guest). So this is not a public sign-up: it exists solely so a fresh
    install has some way to reach the admin screens, and refuses as soon as an
    admin exists. Removing it outright instead would leave a new deployment
    with no route in at all; see scripts/create_admin.py for managing admins
    after bootstrap.
    """
    _enforce_auth_limit(request)

    admin_exists = (
        session.query(User)
        .filter(User.role == Role.ADMIN, User.is_guest.is_(False))
        .count()
        > 0
    )
    if admin_exists:
        raise HTTPException(
            status_code=403,
            detail=(
                "Account registration is closed - the assistant is used anonymously, "
                "no account is needed to ask questions."
            ),
        )

    if len(payload.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )

    email = _normalise_email(payload.email)
    if session.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        # Safe to grant unconditionally: this branch is only reachable while no
        # admin exists, and the endpoint refuses once one does.
        role=Role.ADMIN,
        is_guest=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    return TokenResponse(access_token=create_access_token(user))


@router.post("/login", response_model=TokenResponse)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    _enforce_auth_limit(request)

    email = _normalise_email(form_data.username)
    user = session.query(User).filter(User.email == email).first()

    # Guests hold a random unusable password hash, but refusing them
    # explicitly means an auto-provisioned address can never become a login
    # even if one is ever created with a weak hash by mistake.
    if user is not None and user.is_guest:
        user = None

    # Always calls verify_password, on a real hash either way - see
    # _DUMMY_PASSWORD_HASH's comment for why this can't short-circuit to
    # skipping it for an unknown email.
    password_ok = verify_password(
        form_data.password, user.hashed_password if user is not None else _DUMMY_PASSWORD_HASH
    )
    if user is None or not password_ok:
        # One message for both branches so the endpoint cannot be used to
        # discover which addresses have accounts.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return TokenResponse(access_token=create_access_token(user))
