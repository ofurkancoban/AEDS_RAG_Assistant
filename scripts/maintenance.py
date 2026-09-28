"""Nightly database maintenance: snapshots, rotation, checkpoint pruning.

Two problems this solves.

Backups. app.db holds the only copy of everything a human has put into this
system by hand - staff accounts, approved corpus submissions, and above all
the admin-reviewed answers. None of it can be regenerated from the documents.
Snapshots are taken with VACUUM INTO, which runs inside a read transaction and
therefore produces a consistent, already-compacted copy while the API keeps
serving. Copying the .db file with cp does not: it can catch a write mid-flight
and silently omits the -wal, so the copy is corrupt or stale.

data/chroma (the embedded vector store built from the ingested documents) is
backed up too, as a plain tar.gz - it is technically rebuildable by
re-ingesting data/documents from scratch, but that means re-running every
embed call and losing whichever admin-approved submissions were only ever
applied as chunks, not kept as their own source file.

Growth. The LangGraph checkpointer writes a state snapshot per graph step and
never deletes one, so checkpoints.db grows without bound - and most of it is
not conversation at all but throwaway state from eval runs. Checkpoints are
machine state, not user data: a thread that has not been touched in weeks
cannot be resumed by anyone, so its snapshots are pure cost. Pruning is by age,
read from the checkpoint_id itself (LangGraph mints UUIDv6, which carries its
own creation time), so no separate bookkeeping is needed and threads that are
still active are never touched.

Usage:
    PYTHONPATH=. python scripts/maintenance.py                 # backup + prune
    PYTHONPATH=. python scripts/maintenance.py --dry-run
    PYTHONPATH=. python scripts/maintenance.py --backup-only
    PYTHONPATH=. python scripts/maintenance.py --prune-days 7 --keep 30

Suggested crontab entry (03:30 daily):
    30 3 * * * cd /path/to/AEDS_RAG && PYTHONPATH=. .venv/bin/python \
        scripts/maintenance.py >> data/backups/maintenance.log 2>&1
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import tarfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402

BACKUP_DIR = settings.base_dir / "data" / "backups"

# Offset between the Gregorian epoch UUID timestamps count from (1582-10-15)
# and the Unix epoch, in 100-nanosecond intervals.
_UUID_EPOCH_OFFSET = 0x01B21DD213814000


def checkpoint_created_at(checkpoint_id: str) -> datetime | None:
    """Creation time encoded in a LangGraph checkpoint id.

    UUIDv6 splits its 60-bit timestamp across the first 64 bits in a different
    order than UUIDv1, so Python's own uuid.UUID.time (which assumes the v1
    layout) decodes these to dates centuries out and cannot be used here.
    """
    try:
        value = uuid.UUID(checkpoint_id)
    except (ValueError, AttributeError, TypeError):
        # A NULL checkpoint_id raises TypeError rather than ValueError, and an
        # id this cannot read must never be treated as expired.
        return None
    if value.version != 6:
        return None
    n = value.int
    ticks = ((n >> 96) << 28) | (((n >> 80) & 0xFFFF) << 12) | ((n >> 64) & 0x0FFF)
    seconds = (ticks - _UUID_EPOCH_OFFSET) / 1e7
    try:
        return datetime.fromtimestamp(seconds, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _human(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}GB"


def snapshot(source: Path, keep: int, dry_run: bool) -> Path | None:
    """Write one VACUUM INTO snapshot of `source` and rotate old ones."""
    if not source.exists():
        print(f"  {source.name}: missing, skipped")
        return None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"{source.stem}-{stamp}.db"

    if dry_run:
        print(f"  {source.name}: would snapshot to {target.name} ({_human(source.stat().st_size)} live)")
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        # Parameters are not allowed in VACUUM INTO, and the path is ours, not
        # user input; quotes are doubled anyway so a directory name containing
        # one cannot break out of the literal.
        escaped = str(target).replace("'", "''")
        connection.execute(f"VACUUM INTO '{escaped}'")
    finally:
        connection.close()

    print(f"  {source.name}: {_human(source.stat().st_size)} -> {target.name} ({_human(target.stat().st_size)})")
    _rotate(source.stem, keep, dry_run)
    return target


def snapshot_directory(source: Path, stem: str, keep: int, dry_run: bool) -> Path | None:
    """Write one tar.gz snapshot of a directory and rotate old ones.

    Exists for data/chroma, the embedded vector store: previously nothing
    backed it up at all, only app.db. Unlike snapshot() there is no VACUUM
    INTO equivalent for a directory, so this is a plain tar rather than a
    transaction-consistent copy - a write landing mid-tar could in principle
    make one snapshot inconsistent. Acceptable here because Chroma is only
    ever written by admin actions (ingest/approve/revoke), which are rare and
    already serialized by the admin UI, not by concurrent user traffic.
    """
    if not source.exists():
        print(f"  {source.name}: missing, skipped")
        return None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"{stem}-{stamp}.tar.gz"

    if dry_run:
        print(f"  {source.name}: would snapshot to {target.name}")
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as tar:
        tar.add(source, arcname=source.name)

    print(f"  {source.name}: -> {target.name} ({_human(target.stat().st_size)})")
    _rotate(stem, keep, dry_run, suffix=".tar.gz")
    return target


def _rotate(stem: str, keep: int, dry_run: bool, suffix: str = ".db") -> None:
    """Delete all but the newest `keep` snapshots of one database.

    keep <= 0 disables rotation rather than deleting everything: an operator
    passing 0 almost certainly means "do not rotate", and wiping every backup
    on a misread flag is not a recoverable mistake. Names sort
    chronologically because the timestamp is fixed-width.
    """
    snapshots = sorted(BACKUP_DIR.glob(f"{stem}-*{suffix}"))
    stale = snapshots[:-keep] if keep > 0 else []
    for path in stale:
        if dry_run:
            print(f"    would remove old snapshot {path.name}")
        else:
            path.unlink()
    if stale and not dry_run:
        print(f"    removed {len(stale)} snapshot(s) beyond the most recent {keep}")


def prune_checkpoints(days: int, dry_run: bool) -> int:
    """Delete checkpoint rows older than `days`. Returns the number removed."""
    path = settings.checkpointer_sqlite_path
    if not path.exists():
        print("  checkpoints.db: missing, skipped")
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    connection = sqlite3.connect(str(path))
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        doomed: list[tuple[str, str, str]] = []
        undated = 0
        for thread_id, ns, checkpoint_id in connection.execute(
            "SELECT thread_id, checkpoint_ns, checkpoint_id FROM checkpoints"
        ):
            created = checkpoint_created_at(checkpoint_id)
            if created is None:
                # Age unknown, so it cannot be shown to be expired. Keeping a
                # few extra rows costs disk; deleting a live thread's state
                # would break a conversation mid-flight.
                undated += 1
                continue
            if created < cutoff:
                doomed.append((thread_id, ns, checkpoint_id))

        total = connection.execute("SELECT count(*) FROM checkpoints").fetchone()[0]
        print(
            f"  checkpoints.db: {total} rows, {len(doomed)} older than {days} days"
            + (f", {undated} with unreadable ids (kept)" if undated else "")
        )
        if dry_run or not doomed:
            return 0

        for table in ("checkpoints", "writes", "checkpoint_writes", "checkpoint_blobs"):
            if table not in tables:
                continue
            connection.executemany(
                f"DELETE FROM {table} WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?",
                doomed,
            )
        connection.commit()

        before = path.stat().st_size
        try:
            connection.execute("VACUUM")
            print(f"    reclaimed {_human(before - path.stat().st_size)}")
        except sqlite3.OperationalError as exc:
            # VACUUM needs an exclusive lock; with the API running it may not
            # get one. The rows are still gone, the file just stays large until
            # a run that can take the lock.
            print(f"    rows deleted, VACUUM skipped ({exc})")
        return len(doomed)
    finally:
        connection.close()


def prune_history(chat_days: int, log_days: int, dry_run: bool) -> dict[str, int]:
    """Apply the retention windows to app.db. Returns what was removed.

    Three tables, three different reasons, so three different windows.

    chat_history is a verbatim transcript of what students typed. Nothing in
    the application reads it - no endpoint returns it, no analytics touches it
    - so every row past the window is personal data being kept for nobody.
    The readable value it might one day have does not justify holding a
    student's questions indefinitely by default.

    query_log is different: the admin analytics is built on it, and the
    content-gap list (questions the corpus could not answer) is the most
    direct evidence of what documents are still missing. Its window is
    therefore much longer than the 30 days the analytics screen asks for, so
    a longer look-back stays possible.

    Guest users are the row a visitor gets on first arrival. One is created
    per browser and never removed, so the table grows with every visitor
    forever. Only guests with nothing left attached to them are deleted, which
    is why this runs after the other two.
    """
    from sqlalchemy import text

    from db.models import SessionLocal

    now = datetime.now(timezone.utc)
    chat_cutoff = now - timedelta(days=chat_days)
    log_cutoff = now - timedelta(days=log_days)

    # An anonymous identity is disposable once nothing references it. The NOT
    # EXISTS clauses keep any guest who still has a reviewable submission, a
    # rated answer or a transcript inside the window. The shared
    # "guest@aeds.local" fallback row is excluded by name: it is not one
    # visitor's identity but the one every tokenless caller lands on, and
    # re-creating it on every run would churn ids for no reason.
    orphan_guests = """
          FROM users
         WHERE is_guest = 1
           AND email <> 'guest@aeds.local'
           AND created_at < :cutoff
           AND NOT EXISTS (SELECT 1 FROM chat_history c WHERE c.user_id = users.id)
           AND NOT EXISTS (SELECT 1 FROM query_log q WHERE q.user_id = users.id)
           AND NOT EXISTS (SELECT 1 FROM pending_submissions p WHERE p.submitted_by_id = users.id)
    """

    session = SessionLocal()
    try:
        # The deletes always run; only the commit is conditional. Counting
        # first and deleting second would misreport the dry run, because the
        # guests that become deletable are mostly the ones whose last rows the
        # two deletes above just removed - a preview that said "0 guest users"
        # before a real run removed twenty would be worse than no preview.
        chat_deleted = session.execute(
            text("DELETE FROM chat_history WHERE created_at < :cutoff"), {"cutoff": chat_cutoff}
        ).rowcount
        log_deleted = session.execute(
            text("DELETE FROM query_log WHERE created_at < :cutoff"), {"cutoff": log_cutoff}
        ).rowcount
        guests_deleted = session.execute(
            text("DELETE " + orphan_guests), {"cutoff": chat_cutoff}
        ).rowcount

        counts = {
            "chat_history": chat_deleted,
            "query_log": log_deleted,
            "guest users": guests_deleted,
        }
        verb = "would remove" if dry_run else "removed"
        print(
            f"  chat_history: {verb} {chat_deleted} rows older than {chat_days} days\n"
            f"  query_log:    {verb} {log_deleted} rows older than {log_days} days\n"
            f"  guest users:  {verb} {guests_deleted} with nothing left attached"
        )

        if dry_run:
            session.rollback()
            return {key: 0 for key in counts}

        session.commit()
        return counts
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report what would happen, change nothing")
    parser.add_argument("--keep", type=int, default=14, help="Snapshots to retain per database (default 14)")
    parser.add_argument(
        "--prune-days",
        type=int,
        default=14,
        help="Delete graph checkpoints older than this many days (default 14)",
    )
    parser.add_argument(
        "--chat-history-days",
        type=int,
        default=90,
        help="Keep chat transcripts for this many days (default 90, 0 disables the deletion)",
    )
    parser.add_argument(
        "--query-log-days",
        type=int,
        default=400,
        help="Keep the analytics query log for this many days (default 400, 0 disables)",
    )
    parser.add_argument(
        "--include-checkpoints",
        action="store_true",
        help="Also snapshot checkpoints.db (large, and not user data)",
    )
    parser.add_argument("--backup-only", action="store_true", help="Skip all pruning")
    parser.add_argument("--prune-only", action="store_true", help="Skip snapshots")
    args = parser.parse_args()

    print(f"maintenance run {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

    if not args.prune_only:
        print("backups:")
        snapshot(settings.sqlite_path, args.keep, args.dry_run)
        snapshot_directory(settings.chroma_persist_dir, "chroma", args.keep, args.dry_run)
        # Opt-in: checkpoints.db is machine state, an order of magnitude larger
        # than app.db, and losing it costs nothing a user would notice - the
        # readable conversation lives in app.db's chat_history. Keeping 14
        # nightly copies of it would spend gigabytes to protect nothing.
        if args.include_checkpoints:
            snapshot(settings.checkpointer_sqlite_path, args.keep, args.dry_run)

    if not args.backup_only:
        print("pruning:")
        prune_checkpoints(args.prune_days, args.dry_run)
        # 0 means "keep everything", the same convention --keep uses, so an
        # operator who wants no deletion of user-facing rows can say so
        # without editing the crontab into two commands.
        if args.chat_history_days > 0 or args.query_log_days > 0:
            print("retention:")
            prune_history(
                chat_days=args.chat_history_days or 10**6,
                log_days=args.query_log_days or 10**6,
                dry_run=args.dry_run,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
