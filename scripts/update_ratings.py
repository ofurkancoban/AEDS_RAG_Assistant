"""Refresh course difficulty ratings from the AEDS_ECTS_Tracker project's
ratings.json and sync them onto the Course table here (see
ingestion/ratings.py).

Must run AFTER update_catalog.py in the same night: sync_catalog_to_sql
deletes and recreates every Course row on each catalog refresh, which would
otherwise wipe out that night's difficulty numbers until the next ratings
run picked them back up. Unlike the catalog, ratings.json isn't a document -
there's nothing to re-ingest into Chroma here, just a SQL sync.

Usage:
    PYTHONPATH=. python scripts/update_ratings.py

Suggested crontab entry (02:05 daily, just after update_catalog.py's 02:00):
    5 2 * * * cd /path/to/AEDS_RAG && PYTHONPATH=. .venv/bin/python \
        scripts/update_ratings.py >> data/backups/update_ratings.log 2>&1
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.ratings import fetch_ratings, sync_ratings_to_sql  # noqa: E402


def main() -> int:
    print(f"ratings update run {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    try:
        ratings = fetch_ratings()
    except Exception as exc:  # noqa: BLE001 - this is a leaf script, not a library call
        print(f"could not fetch ratings.json: {exc}", file=sys.stderr)
        return 1

    updated = sync_ratings_to_sql(ratings)
    print(f"synced difficulty ratings for {updated} course(s) ({len(ratings)} in ratings.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
