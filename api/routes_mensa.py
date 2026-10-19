"""Canteen photos and pictograms, served from this server.

The menu cards (graph/mensa.py) show the Studierendenwerk's dish photos and
diet icons. They are fetched once from the menu server and kept on disk, so
a student's browser never contacts that third-party host (no address or
referrer leaves this site) and the photos keep loading if the menu server
is slow. Only the menu server's own photo and icon paths are accepted, so
this cannot be used to fetch anything else.
"""

import hashlib
import re

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from api.rate_limit import RateLimiter, client_ip
from config import settings
from ingestion.mensa import BASE_URL

router = APIRouter(prefix="/mensa", tags=["mensa"])

_ALLOWED = re.compile(r"assets/(fotos|icons)/[A-Za-z0-9_\-./+%]+\.(jpe?g|png)", re.I)
_MAX_BYTES = 5 * 1024 * 1024
# Only fetches that miss the disk cache count: a page of cards is about
# twenty images, and each is fetched from the menu server once.
_fetch_limiter = RateLimiter("mensa_image_fetch", [(200, 3600)])


def _cache_dir():
    path = settings.documents_dir.parent / "mensa_images"
    path.mkdir(parents=True, exist_ok=True)
    return path


class ImageUnavailable(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _target(src: str):
    if not _ALLOWED.fullmatch(src) or ".." in src:
        raise ImageUnavailable(400, "Not a canteen image path")
    suffix = ".png" if src.lower().endswith(".png") else ".jpg"
    return _cache_dir() / (hashlib.sha256(src.encode()).hexdigest()[:32] + suffix)


def cached_image(src: str, allow_fetch=lambda: True):
    """The image's file on disk, fetched from the menu server the first time.
    Also used by the Telegram bot (photos) and the morning prefetch."""
    target = _target(src)
    if target.exists():
        return target
    if not allow_fetch():
        raise ImageUnavailable(429, "Too many image requests")
    try:
        response = httpx.get(f"{BASE_URL}/{src}", timeout=15, follow_redirects=False)
    except httpx.HTTPError:
        raise ImageUnavailable(502, "The menu server did not answer")
    content_type = response.headers.get("content-type", "")
    if response.status_code != 200 or not content_type.startswith("image/") or len(response.content) > _MAX_BYTES:
        raise ImageUnavailable(404, "Image not available")
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(response.content)
    tmp.replace(target)
    return target


@router.get("/image")
def mensa_image(src: str, request: Request):
    try:
        target = cached_image(src, allow_fetch=lambda: _fetch_limiter.check_and_record(client_ip(request)))
    except ImageUnavailable as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)
    return FileResponse(
        target,
        media_type="image/png" if target.suffix == ".png" else "image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )
