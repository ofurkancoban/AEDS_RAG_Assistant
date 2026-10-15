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


@router.get("/image")
def mensa_image(src: str, request: Request):
    if not _ALLOWED.fullmatch(src) or ".." in src:
        raise HTTPException(status_code=400, detail="Not a canteen image path")
    suffix = ".png" if src.lower().endswith(".png") else ".jpg"
    target = _cache_dir() / (hashlib.sha256(src.encode()).hexdigest()[:32] + suffix)

    if not target.exists():
        if not _fetch_limiter.check_and_record(client_ip(request)):
            raise HTTPException(status_code=429, detail="Too many image requests")
        try:
            response = httpx.get(f"{BASE_URL}/{src}", timeout=15, follow_redirects=False)
        except httpx.HTTPError:
            raise HTTPException(status_code=502, detail="The menu server did not answer")
        content_type = response.headers.get("content-type", "")
        if response.status_code != 200 or not content_type.startswith("image/") or len(response.content) > _MAX_BYTES:
            raise HTTPException(status_code=404, detail="Image not available")
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(response.content)
        tmp.replace(target)

    return FileResponse(
        target,
        media_type="image/png" if suffix == ".png" else "image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )
