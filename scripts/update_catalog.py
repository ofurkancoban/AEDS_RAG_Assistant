"""Refresh data/documents/catalog.csv from Stud.IP and re-ingest it if it
changed.

Wraps scripts/fetch_catalog.py (a stdlib-only scraper of the AEDS study
programme's Stud.IP listing) with the re-ingestion step this project needs:
fetch_catalog.py only rewrites the CSV in place - updating rows for modules
that changed, adding newly offered ones, and preserving hand-maintained
columns like `compulsory` for the rest. Getting that change into Chroma and
the Course SQL table (see db/models.Course) still goes through the normal
ingest_and_record_file path, which is a no-op when the scrape produced no
actual change (same file hash) - so running this nightly costs nothing on a
quiet night.

Usage:
    PYTHONPATH=. python scripts/update_catalog.py
    PYTHONPATH=. python scripts/update_catalog.py --skip-ingest   # fetch only

Suggested crontab entry (02:00 daily, ahead of source_refresh.py and
maintenance.py):
    0 2 * * * cd /path/to/AEDS_RAG && PYTHONPATH=. .venv/bin/python \
        scripts/update_catalog.py >> data/backups/update_catalog.log 2>&1
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402

CATALOG_PATH = settings.documents_dir / "catalog.csv"
FETCH_SCRIPT = Path(__file__).resolve().parent / "fetch_catalog.py"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Fetch and rewrite catalog.csv, but skip re-ingesting it",
    )
    args = parser.parse_args()

    print(f"catalog update run {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

    result = subprocess.run(
        [sys.executable, str(FETCH_SCRIPT), str(CATALOG_PATH)],
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr, end="")
        return result.returncode

    if args.skip_ingest:
        print("--skip-ingest: not re-ingesting")
        return 0

    from db.models import SessionLocal
    from ingestion.chunker import ingest_and_record_file

    session = SessionLocal()
    try:
        chunk_count = ingest_and_record_file(CATALOG_PATH, session)
    finally:
        session.close()

    if chunk_count is None:
        print("catalog.csv unchanged, not re-ingested")
    else:
        print(f"catalog.csv re-ingested: {chunk_count} chunks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
