"""scripts/offsite_backup.py: encrypted snapshots go to R2, plain ones never
do, and only the newest r2_keep copies of each kind are kept there."""

import pytest

from config import settings
from scripts import offsite_backup


class _FakeR2:
    def __init__(self, keys=()):
        self.objects = set(keys)

    def upload_file(self, path, bucket, key):
        self.objects.add(key)

    def get_paginator(self, name):
        fake = self

        class _Pages:
            def paginate(self, Bucket):
                return [{"Contents": [{"Key": k} for k in sorted(fake.objects)]}]

        return _Pages()

    def delete_object(self, Bucket, Key):
        self.objects.discard(Key)


def _snapshot(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"ciphertext")
    return path


def test_uploads_encrypted_snapshots_and_keeps_the_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_encryption_key", "k")
    monkeypatch.setattr(settings, "r2_keep", 2)
    r2 = _FakeR2({"app-20261001-013000.db.enc", "app-20261002-013000.db.enc", "chroma-20261002-013000.tar.gz.enc"})

    sent = offsite_backup.upload(
        [_snapshot(tmp_path, "app-20261003-013000.db.enc"), _snapshot(tmp_path, "chroma-20261003-013000.tar.gz.enc")],
        client=r2,
    )

    assert sent == ["app-20261003-013000.db.enc", "chroma-20261003-013000.tar.gz.enc"]
    assert r2.objects == {
        "app-20261002-013000.db.enc", "app-20261003-013000.db.enc",
        "chroma-20261002-013000.tar.gz.enc", "chroma-20261003-013000.tar.gz.enc",
    }


def test_refuses_without_an_encryption_key(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_encryption_key", "")
    r2 = _FakeR2()
    with pytest.raises(RuntimeError):
        offsite_backup.upload([_snapshot(tmp_path, "app-20261003-013000.db.enc")], client=r2)
    assert not r2.objects


def test_refuses_a_plain_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_encryption_key", "k")
    r2 = _FakeR2()
    with pytest.raises(RuntimeError):
        offsite_backup.upload([_snapshot(tmp_path, "app-20261003-013000.db")], client=r2)
    assert not r2.objects


def test_keep_zero_deletes_nothing(monkeypatch):
    monkeypatch.setattr(settings, "r2_keep", 0)
    r2 = _FakeR2({"app-20261001-013000.db.enc"})
    assert offsite_backup.prune(r2) == []
    assert r2.objects == {"app-20261001-013000.db.enc"}
