import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from config import settings
from db.models import Role, User, get_session

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

GUEST_EMAIL = "guest@aeds.local"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


def create_access_token(user: User, expires_minutes: int | None = None) -> str:
    minutes = expires_minutes if expires_minutes is not None else settings.jwt_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "is_guest": bool(user.is_guest),
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = session.get(User, int(user_id))
    if user is None:
        raise credentials_exception
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def create_guest_user(session: Session) -> User:
    """Mint a fresh, isolated identity for one anonymous visitor.

    Each visitor gets their own row (and therefore their own threads, chat
    history, and rate-limit bucket). The password hash is deliberately
    unusable: guests authenticate only by holding their token, and
    /auth/login refuses is_guest accounts outright.
    """
    guest = User(
        email=f"guest-{uuid.uuid4()}@aeds.local",
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        role=Role.USER,
        is_guest=True,
    )
    session.add(guest)
    session.commit()
    session.refresh(guest)
    return guest


def get_or_create_shared_guest_user(session: Session) -> User:
    """Fallback identity for requests that carry no token at all.

    Clients that go through the UI always hold a guest token (see
    /auth/guest), so this covers only direct API calls. It is deliberately a
    single shared row rather than a new one per request, which would let an
    unauthenticated loop fill the users table.
    """
    guest = session.query(User).filter(User.email == GUEST_EMAIL).first()
    if guest is not None:
        return guest

    guest = User(
        email=GUEST_EMAIL,
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        role=Role.USER,
        is_guest=True,
    )
    session.add(guest)
    session.commit()
    session.refresh(guest)
    return guest


def get_current_user_or_guest(
    token: str | None = Depends(optional_oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    """Allows anyone to chat without registering, while still identifying who
    is who: a token (registered account or guest) names one specific user, and
    only a completely tokenless caller falls back to the shared identity.

    A token that is present but unusable is a 401, not a silent downgrade to
    the shared guest. Falling back would let a client whose token had expired
    keep working while quietly writing into a different identity's history -
    and would leave it no way to notice it should re-establish a session.
    """
    if token is None:
        return get_or_create_shared_guest_user(session)

    expired_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expired or invalid - start a new session",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
    except JWTError:
        raise expired_exception

    user = session.get(User, int(user_id)) if user_id else None
    if user is None:
        raise expired_exception
    return user
