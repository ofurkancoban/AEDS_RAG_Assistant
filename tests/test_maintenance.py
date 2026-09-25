"""Backups and checkpoint retention.

Both halves are destructive-adjacent - one writes files and rotates old ones
away, the other deletes rows - so the behaviour worth pinning is the boundary:
what gets kept.
"""

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from scripts import maintenance


def _uuid6_at(moment: datetime) -> str:
    """Mint a UUIDv6 carrying a chosen timestamp, the way LangGraph mints them."""
    ticks = int(moment.timestamp() * 1e7) + maintenance._UUID_EPOCH_OFFSET
    time_high = (ticks >> 28) & 0xFFFFFFFF
    time_mid = (ticks >> 12) & 0xFFFF
    time_low = ticks & 0x0FFF
    value = (
        (time_high << 96)
        | (time_mid << 80)
        | (6 << 76)
        | (time_low << 64)
        | (0x8000 << 48)
        | 0x123456789ABC
    )
    return str(uuid.UUID(int=value))


def test_a_checkpoint_id_reveals_its_own_age():
    moment = datetime(2026, 8, 1, 12, 30, tzinfo=timezone.utc)
    decoded = maintenance.checkpoint_created_at(_uuid6_at(moment))
    assert decoded is not None
    # Python's uuid.UUID.time assumes the v1 field order and decodes these to
    # dates centuries out, which is why this is computed by hand.
    assert abs((decoded - moment).total_seconds()) < 1


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "", None, str(uuid.uuid4())])
def test_an_unreadable_checkpoint_id_has_no_age(bad_id):
    # uuid4 carries no timestamp at all, so it must not be guessed at.
    assert maintenance.checkpoint_created_at(bad_id) is None


def _make_checkpoint_db(path, ages_in_days):
    connection = sqlite3.connect(str(path))
    connection.execute(
        "CREATE TABLE checkpoints (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT)"
    )
    connection.execute(
        "CREATE TABLE writes (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT)"
    )
    now = datetime.now(timezone.utc)
    for index, days in enumerate(ages_in_days):
        checkpoint_id = _uuid6_at(now - timedelta(days=days))
        connection.execute(
            "INSERT INTO checkpoints VALUES (?, '', ?)", (f"thread-{index}", checkpoint_id)
        )
        connection.execute("INSERT INTO writes VALUES (?, '', ?)", (f"thread-{index}", checkpoint_id))
    connection.commit()
    connection.close()


def test_pruning_removes_only_what_is_older_than_the_cutoff(tmp_path, monkeypatch):
    path = tmp_path / "checkpoints.db"
    _make_checkpoint_db(path, ages_in_days=[30, 20, 5, 1])
    monkeypatch.setattr(maintenance.settings, "checkpointer_sqlite_path", path)

    removed = maintenance.prune_checkpoints(days=14, dry_run=False)
    assert removed == 2

    connection = sqlite3.connect(str(path))
    try:
        assert connection.execute("SELECT count(*) FROM checkpoints").fetchone()[0] == 2
        # The companion table has to be cleaned with it or the writes outlive
        # the state they belong to.
        assert connection.execute("SELECT count(*) FROM writes").fetchone()[0] == 2
    finally:
        connection.close()


def test_a_dry_run_deletes_nothing(tmp_path, monkeypatch):
    path = tmp_path / "checkpoints.db"
    _make_checkpoint_db(path, ages_in_days=[30, 30])
    monkeypatch.setattr(maintenance.settings, "checkpointer_sqlite_path", path)

    assert maintenance.prune_checkpoints(days=1, dry_run=True) == 0

    connection = sqlite3.connect(str(path))
    try:
        assert connection.execute("SELECT count(*) FROM checkpoints").fetchone()[0] == 2
    finally:
        connection.close()


def test_a_snapshot_is_a_readable_standalone_copy(tmp_path, monkeypatch):
    source = tmp_path / "app.db"
    connection = sqlite3.connect(str(source))
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE answers (id INTEGER, text TEXT)")
    connection.execute("INSERT INTO answers VALUES (1, 'admin-approved wording')")
    connection.commit()
    # Left open and uncheckpointed on purpose: this is the state a plain file
    # copy gets wrong, because the committed row is still only in the -wal.
    monkeypatch.setattr(maintenance, "BACKUP_DIR", tmp_path / "backups")

    target = maintenance.snapshot(source, keep=5, dry_run=False)
    connection.close()

    assert target is not None and target.exists()
    copy = sqlite3.connect(str(target))
    try:
        assert copy.execute("SELECT text FROM answers").fetchone()[0] == "admin-approved wording"
        assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        copy.close()


def test_rotation_keeps_the_most_recent_snapshots(tmp_path, monkeypatch):
    backups = tmp_path / "backups"
    backups.mkdir()
    monkeypatch.setattr(maintenance, "BACKUP_DIR", backups)
    for stamp in ("20260101-000000", "20260102-000000", "20260103-000000"):
        (backups / f"app-{stamp}.db").write_bytes(b"")

    maintenance._rotate("app", keep=2, dry_run=False)

    remaining = sorted(p.name for p in backups.glob("app-*.db"))
    assert remaining == ["app-20260102-000000.db", "app-20260103-000000.db"]


def test_rotation_does_not_touch_another_database_s_snapshots(tmp_path, monkeypatch):
    backups = tmp_path / "backups"
    backups.mkdir()
    monkeypatch.setattr(maintenance, "BACKUP_DIR", backups)
    for name in (
        "app-20260101-000000.db",
        "app-20260102-000000.db",
        "checkpoints-20260101-000000.db",
    ):
        (backups / name).write_bytes(b"")

    maintenance._rotate("app", keep=1, dry_run=False)

    remaining = sorted(p.name for p in backups.glob("*.db"))
    # Rotation is per database; the glob must not reach across to another's
    # history.
    assert remaining == ["app-20260102-000000.db", "checkpoints-20260101-000000.db"]


def test_keeping_zero_means_keeping_everything(tmp_path, monkeypatch):
    backups = tmp_path / "backups"
    backups.mkdir()
    monkeypatch.setattr(maintenance, "BACKUP_DIR", backups)
    (backups / "app-20260101-000000.db").write_bytes(b"")

    maintenance._rotate("app", keep=0, dry_run=False)

    # An operator asking to keep nothing almost certainly means "do not rotate",
    # and deleting every backup on a misread flag is not a recoverable mistake.
    assert (backups / "app-20260101-000000.db").exists()
