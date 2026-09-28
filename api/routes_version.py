"""Public, unauthenticated: the version badge and changelog popup need this
before a visitor has signed in at all, same as /health."""

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
