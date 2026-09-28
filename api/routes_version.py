"""Public, unauthenticated: the version badge, changelog popup, and visitor
counter all need this before a visitor has signed in at all, same as
/health."""

from fastapi import APIRouter
from pydantic import BaseModel

from changelog import read_changelog

router = APIRouter(tags=["version"])


class ChangelogEntryOut(BaseModel):
    version: str
    date: str
    sections: dict[str, list[str]]


class VersionOut(BaseModel):
    version: str
    changelog: list[ChangelogEntryOut]


@router.get("/version", response_model=VersionOut)
def get_version():
    entries = read_changelog()
    return VersionOut(version=entries[0]["version"] if entries else "0.0.0", changelog=entries)


class VisitorsOut(BaseModel):
    unique_visitors: int


@router.get("/visitors", response_model=VisitorsOut)
def get_visitor_count():
    """Every distinct browser that has ever used the app: one User row per
    guest identity (see api/auth.py's create_guest_user, minted once and
    reused from localStorage on later visits - a returning visitor does not
    add to this) plus every registered account. Excludes GUEST_EMAIL, the
    single shared fallback row for tokenless direct API calls - it is one
    bucket shared across possibly many callers, not one visitor."""
    from api.auth import GUEST_EMAIL
    from db.models import SessionLocal, User

    session = SessionLocal()
    try:
        count = session.query(User).filter(User.email != GUEST_EMAIL).count()
    finally:
        session.close()
    return VisitorsOut(unique_visitors=count)
