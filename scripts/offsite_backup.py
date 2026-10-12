"""Copy the nightly snapshots to a Cloudflare R2 bucket.

data/backups/ lives on the same disk as the data it protects, so it covers a
bad migration or an accidental delete but not a lost disk. This uploads each
new snapshot (app.db and the Chroma tarball) to R2 and keeps the newest
settings.r2_keep copies of each there.

Only encrypted snapshots (*.enc, see scripts/maintenance.py's
_encrypt_backup) are uploaded; with no BACKUP_ENCRYPTION_KEY set the upload
is refused, so students' conversations never leave the server in plain text.

Called by scripts/maintenance.py after the snapshots are written. Restore:
    PYTHONPATH=. python scripts/offsite_backup.py --list
    PYTHONPATH=. python scripts/offsite_backup.py --download app-20261013-013002.db.enc
then decrypt it as described in docs/deployment.md ("Backups").
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402

_STEM_RE = re.compile(r"^(?P<stem>.+?)-\d{8}-\d{6}\.")


def enabled() -> bool:
    return bool(
        settings.r2_bucket
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.cloudflare_account_id
    )


def _client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.cloudflare_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def upload(paths: list[Path], client=None) -> list[str]:
    """Upload the given snapshots and prune old copies; returns what was
    uploaded. Raises on any failure so the caller can alert."""
    if not settings.backup_encryption_key:
        raise RuntimeError("BACKUP_ENCRYPTION_KEY is not set; refusing to upload unencrypted backups")
    client = client or _client()
    uploaded = []
    for path in paths:
        if path is None:
            continue
        if not path.name.endswith(".enc"):
            raise RuntimeError(f"{path.name} is not encrypted; refusing to upload it")
        client.upload_file(str(path), settings.r2_bucket, path.name)
        uploaded.append(path.name)
    prune(client)
    return uploaded


def _keys(client) -> list[str]:
    keys = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=settings.r2_bucket):
        keys += [item["Key"] for item in page.get("Contents", [])]
    return keys


def prune(client) -> list[str]:
    """Keep the newest r2_keep copies per snapshot kind (app, chroma...).
    The timestamp in each name sorts chronologically."""
    if settings.r2_keep <= 0:
        return []  # 0 means keep everything, as --keep does in maintenance.py
    by_stem: dict[str, list[str]] = {}
    for key in _keys(client):
        match = _STEM_RE.match(key)
        if match:
            by_stem.setdefault(match["stem"], []).append(key)
    removed = []
    for keys in by_stem.values():
        for key in sorted(keys)[: -settings.r2_keep]:
            client.delete_object(Bucket=settings.r2_bucket, Key=key)
            removed.append(key)
    return removed


def main() -> int:
    if not enabled():
        print("R2 is not configured (R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, CLOUDFLARE_ACCOUNT_ID).")
        return 1
    client = _client()
    if "--list" in sys.argv:
        for key in sorted(_keys(client)):
            print(key)
        return 0
    if "--download" in sys.argv:
        name = sys.argv[sys.argv.index("--download") + 1]
        client.download_file(settings.r2_bucket, name, name)
        print(f"downloaded {name}")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
