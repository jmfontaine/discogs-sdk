"""Unit tests for cache backends (MemoryCache and SQLiteCache)."""

from __future__ import annotations

import functools
import gc
import logging
import os
import sqlite3
import stat
import subprocess
import sys
import time
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from discogs_sdk._cache import MemoryCache, SQLiteCache
from tests.conftest import exclusive_lock


class TestMemoryCache:
    def test_set_get_roundtrip(self):
        cache = MemoryCache(ttl=60)
        cache.set(
            "GET:http://x/1", 200, {"content-type": "application/json"}, b'{"id":1}'
        )
        result = cache.get("GET:http://x/1")
        assert result == (200, {"content-type": "application/json"}, b'{"id":1}')

    def test_miss_returns_none(self):
        cache = MemoryCache(ttl=60)
        assert cache.get("GET:http://x/missing") is None

    def test_expired_entry_returns_none(self):
        cache = MemoryCache(ttl=0.01)
        cache.set("GET:http://x/1", 200, {}, b"ok")
        time.sleep(0.02)
        assert cache.get("GET:http://x/1") is None

    def test_clear_removes_all(self):
        cache = MemoryCache(ttl=60)
        cache.set("GET:http://x/1", 200, {}, b"a")
        cache.set("GET:http://x/2", 200, {}, b"b")
        cache.clear()
        assert cache.get("GET:http://x/1") is None
        assert cache.get("GET:http://x/2") is None

    def test_close_is_noop(self):
        cache = MemoryCache(ttl=60)
        cache.set("GET:http://x/1", 200, {}, b"a")
        cache.close()  # should not raise


class TestSQLiteCache:
    def test_set_get_roundtrip(self, tmp_path):
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        cache.set(
            "GET:http://x/1", 200, {"content-type": "application/json"}, b'{"id":1}'
        )
        result = cache.get("GET:http://x/1")
        assert result is not None
        status, headers, body = result
        assert status == 200
        assert headers == {"content-type": "application/json"}
        assert body == b'{"id":1}'
        cache.close()

    def test_miss_returns_none(self, tmp_path):
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        assert cache.get("GET:http://x/missing") is None
        cache.close()

    def test_expired_entry_returns_none(self, tmp_path):
        cache = SQLiteCache(ttl=0.01, cache_dir=tmp_path)
        cache.set("GET:http://x/1", 200, {}, b"ok")
        time.sleep(0.02)
        assert cache.get("GET:http://x/1") is None
        cache.close()

    def test_clear_removes_all(self, tmp_path):
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        cache.set("GET:http://x/1", 200, {}, b"a")
        cache.set("GET:http://x/2", 200, {}, b"b")
        cache.clear()
        assert cache.get("GET:http://x/1") is None
        assert cache.get("GET:http://x/2") is None
        cache.close()

    def test_creates_cache_dir(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        cache = SQLiteCache(ttl=60, cache_dir=nested)
        assert nested.is_dir()
        cache.close()

    def test_data_persists_across_close_reopen(self, tmp_path):
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        cache.set("GET:http://x/1", 200, {"k": "v"}, b"data")
        cache.close()

        # Reopen the same database
        cache2 = SQLiteCache(ttl=60, cache_dir=tmp_path)
        result = cache2.get("GET:http://x/1")
        assert result is not None
        assert result == (200, {"k": "v"}, b"data")
        cache2.close()

    def test_expired_entry_deleted_on_get(self, tmp_path):
        """Expired rows are lazily deleted on get()."""
        cache = SQLiteCache(ttl=1, cache_dir=tmp_path)
        # Insert with a past expiry by patching time.time
        with patch("discogs_sdk._cache.time.time", return_value=1000.0):
            cache.set("GET:http://x/1", 200, {}, b"old")
        # Now time is past expiry (1000 + 1 = 1001)
        with patch("discogs_sdk._cache.time.time", return_value=1002.0):
            assert cache.get("GET:http://x/1") is None
        # Row should be gone from the database
        assert cache._db is not None
        row = cache._db.execute("SELECT count(*) FROM cache_entries").fetchone()
        assert row[0] == 0
        cache.close()


class TestSQLiteCacheClosed:
    @pytest.mark.parametrize(
        "call",
        [
            lambda c: c.get("GET:http://x/1"),
            lambda c: c.set("GET:http://x/1", 200, {}, b"a"),
            lambda c: c.clear(),
        ],
        ids=["get", "set", "clear"],
    )
    def test_use_after_close_raises_runtime_error(self, tmp_path, call):
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        cache.close()
        with pytest.raises(RuntimeError, match="closed"):
            call(cache)

    def test_close_is_idempotent(self, tmp_path):
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        cache.close()
        cache.close()

    def test_use_after_close_raises_runtime_error_under_optimize(self, tmp_path):
        """``python -O`` strips asserts; the closed check must not depend on one."""
        script = (
            "import sys\n"
            "from pathlib import Path\n"
            "from discogs_sdk._cache import SQLiteCache\n"
            "cache = SQLiteCache(ttl=60, cache_dir=Path(sys.argv[1]))\n"
            "cache.close()\n"
            "for call in (lambda: cache.get('k'),"
            " lambda: cache.set('k', 200, {}, b''), cache.clear):\n"
            "    try:\n"
            "        call()\n"
            "    except RuntimeError as exc:\n"
            "        print(type(exc).__name__, exc)\n"
        )
        result = subprocess.run(
            [sys.executable, "-O", "-c", script, str(tmp_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.splitlines() == ["RuntimeError SQLiteCache is closed"] * 3


class TestSQLiteCacheErrors:
    """A failing database degrades to misses and skipped stores, never raises."""

    def test_set_while_locked_skips_the_store(
        self, tmp_path, caplog, fast_sqlite_busy_timeout
    ):
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        caplog.set_level(logging.WARNING, logger="discogs_sdk")
        with exclusive_lock(tmp_path):
            cache.set("GET:http://x/1", 200, {}, b"a")
            # The failed write was rolled back, so this connection holds no lock.
            assert cache._db is not None
            assert not cache._db.in_transaction
        assert "database is locked" in caplog.text
        assert str(tmp_path / "cache.db") in caplog.text
        assert cache.get("GET:http://x/1") is None
        cache.set("GET:http://x/1", 200, {}, b"b")
        assert cache.get("GET:http://x/1") == (200, {}, b"b")
        cache.close()

    def test_get_of_expired_entry_while_locked_returns_none(
        self, tmp_path, caplog, fast_sqlite_busy_timeout
    ):
        """An expired hit deletes its row, so even a read needs the write lock."""
        cache = SQLiteCache(ttl=1, cache_dir=tmp_path)
        with patch("discogs_sdk._cache.time.time", return_value=1000.0):
            cache.set("GET:http://x/1", 200, {}, b"old")
        caplog.set_level(logging.WARNING, logger="discogs_sdk")
        with exclusive_lock(tmp_path):
            assert cache.get("GET:http://x/1") is None
            assert cache._db is not None
            assert not cache._db.in_transaction
        assert "database is locked" in caplog.text
        cache.close()

    def test_clear_while_locked_keeps_entries(
        self, tmp_path, caplog, fast_sqlite_busy_timeout
    ):
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        cache.set("GET:http://x/1", 200, {}, b"a")
        caplog.set_level(logging.WARNING, logger="discogs_sdk")
        with exclusive_lock(tmp_path):
            cache.clear()
        assert "database is locked" in caplog.text
        assert cache.get("GET:http://x/1") == (200, {}, b"a")
        cache.close()

    def test_garbage_file_degrades_to_misses(self, tmp_path, caplog):
        (tmp_path / "cache.db").write_bytes(b"this is not a database" * 64)
        with caplog.at_level(logging.WARNING, logger="discogs_sdk"):
            cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
            cache.set("GET:http://x/1", 200, {}, b"a")
            assert cache.get("GET:http://x/1") is None
            cache.clear()
        assert "file is not a database" in caplog.text
        cache.close()


class TestSQLiteCachePragmas:
    def test_uses_wal_and_normal_synchronous(self, tmp_path):
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        assert cache._db is not None
        assert cache._db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert cache._db.execute("PRAGMA synchronous").fetchone()[0] == 1
        cache.close()

    def test_lock_at_startup_leaves_defaults_and_a_working_cache(
        self, tmp_path, caplog, fast_sqlite_busy_timeout
    ):
        """Without the lock neither WAL nor the table can be set up at first."""
        caplog.set_level(logging.WARNING, logger="discogs_sdk")
        with exclusive_lock(tmp_path):
            cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        assert "journal_mode=WAL" in caplog.text
        assert "create the cache table" in caplog.text
        # The table is created by the first operation that gets the lock.
        cache.set("GET:http://x/1", 200, {}, b"a")
        assert cache.get("GET:http://x/1") == (200, {}, b"a")
        assert cache._db is not None
        assert cache._db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        cache.close()

    def test_declined_wal_is_logged(self, tmp_path, caplog, monkeypatch):
        """Without raising, SQLite answers a mode it cannot use with the old one."""

        class DeclinesWal(sqlite3.Connection):
            def execute(self, sql, *args):
                if sql == "PRAGMA journal_mode=WAL":
                    sql = "PRAGMA journal_mode"
                return super().execute(sql, *args)

        monkeypatch.setattr(
            sqlite3, "connect", functools.partial(sqlite3.connect, factory=DeclinesWal)
        )
        caplog.set_level(logging.WARNING, logger="discogs_sdk")
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        assert "mode stays delete" in caplog.text
        cache.set("GET:http://x/1", 200, {}, b"a")
        assert cache.get("GET:http://x/1") == (200, {}, b"a")
        cache.close()


@contextmanager
def umask(mask: int) -> Iterator[None]:
    previous = os.umask(mask)
    try:
        yield
    finally:
        os.umask(previous)


def mode_of(path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes and ownership")
class TestSQLiteCachePermissions:
    """The database holds private responses, so only its owner may reach it."""

    def test_created_directories_are_private_even_under_umask_0(self, tmp_path):
        nested = tmp_path / "a" / "b"
        with umask(0):
            cache = SQLiteCache(ttl=60, cache_dir=nested)
        assert mode_of(nested) == 0o700
        assert mode_of(tmp_path / "a") == 0o700
        cache.close()

    def test_existing_directory_keeps_its_mode(self, tmp_path):
        tmp_path.chmod(0o755)
        SQLiteCache(ttl=60, cache_dir=tmp_path).close()
        assert mode_of(tmp_path) == 0o755

    def test_new_database_is_private_even_under_umask_0(self, tmp_path):
        with umask(0):
            cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
            cache.set("GET:http://x/1", 200, {}, b"a")
            files = sorted(tmp_path.glob("cache.db*"))
            # WAL mode keeps its sidecars around while the connection is open.
            assert [f.name for f in files] == [
                "cache.db",
                "cache.db-shm",
                "cache.db-wal",
            ]
            assert mode_of(tmp_path / "cache.db") == 0o600
            assert all(mode_of(f) & 0o077 == 0 for f in files)
            cache.close()

    def test_world_readable_database_is_tightened(self, tmp_path):
        SQLiteCache(ttl=60, cache_dir=tmp_path).close()
        (tmp_path / "cache.db").chmod(0o644)
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        assert mode_of(tmp_path / "cache.db") == 0o600
        cache.set("GET:http://x/1", 200, {}, b"a")
        assert cache.get("GET:http://x/1") == (200, {}, b"a")
        cache.close()

    def test_world_readable_sidecar_is_tightened(self, tmp_path):
        SQLiteCache(ttl=60, cache_dir=tmp_path).close()
        wal = tmp_path / "cache.db-wal"
        wal.touch()
        wal.chmod(0o644)
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        assert mode_of(wal) == 0o600
        cache.close()

    def test_symlinked_database_is_refused(self, tmp_path):
        target = tmp_path / "elsewhere.db"
        target.write_bytes(b"not yours")
        target.chmod(0o644)
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "cache.db").symlink_to(target)
        with pytest.raises(PermissionError, match="cache.db"):
            SQLiteCache(ttl=60, cache_dir=cache_dir)
        assert target.read_bytes() == b"not yours"
        assert mode_of(target) == 0o644

    def test_symlinked_sidecar_is_refused(self, tmp_path):
        target = tmp_path / "elsewhere"
        target.write_bytes(b"")
        target.chmod(0o644)
        cache_dir = tmp_path / "cache"
        SQLiteCache(ttl=60, cache_dir=cache_dir).close()
        (cache_dir / "cache.db-wal").symlink_to(target)
        with pytest.raises(PermissionError, match="cache.db-wal"):
            SQLiteCache(ttl=60, cache_dir=cache_dir)
        assert mode_of(target) == 0o644

    @pytest.mark.parametrize(
        "make",
        [
            os.mkdir,
            os.mkfifo,
            # Read-only for its owner, so it takes the read-only open path.
            functools.partial(os.mkfifo, mode=0o444),
        ],
        ids=["directory", "fifo", "read-only-fifo"],
    )
    def test_database_that_is_not_a_regular_file_is_refused(self, tmp_path, make):
        make(tmp_path / "cache.db")
        with pytest.raises(PermissionError, match="cache.db"):
            SQLiteCache(ttl=60, cache_dir=tmp_path)

    def test_database_owned_by_someone_else_is_refused(self, tmp_path, monkeypatch):
        SQLiteCache(ttl=60, cache_dir=tmp_path).close()
        (tmp_path / "cache.db").chmod(0o644)
        monkeypatch.setattr(os, "geteuid", lambda: os.stat(tmp_path).st_uid + 1)
        with pytest.raises(PermissionError, match="cache.db"):
            SQLiteCache(ttl=60, cache_dir=tmp_path)
        # Someone else's file is reported, never chmodded.
        assert mode_of(tmp_path / "cache.db") == 0o644

    def test_vetting_keeps_the_locks_of_an_open_connection(self, tmp_path):
        """Closing any descriptor of a file drops every POSIX lock the process holds
        on it, so vetting must not open a database another connection uses."""
        first = SQLiteCache(ttl=60, cache_dir=tmp_path)
        first.set("GET:http://x/1", 200, {}, b"a")
        SQLiteCache(ttl=60, cache_dir=tmp_path).close()
        # A connection that closes believing it is the last one checkpoints and
        # deletes the WAL file that `first` still uses.
        script = (
            "import sqlite3, sys\n"
            "db = sqlite3.connect(sys.argv[1])\n"
            "db.execute('SELECT count(*) FROM cache_entries').fetchall()\n"
            "db.close()\n"
        )
        subprocess.run(
            [sys.executable, "-c", script, str(tmp_path / "cache.db")], check=True
        )
        assert (tmp_path / "cache.db-wal").exists()
        assert first.get("GET:http://x/1") == (200, {}, b"a")
        first.close()

    def test_a_cache_collected_unclosed_is_vetted_again(self, tmp_path):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            SQLiteCache(ttl=60, cache_dir=tmp_path)  # dropped without close()
            gc.collect()
        (tmp_path / "cache.db").chmod(0o644)
        SQLiteCache(ttl=60, cache_dir=tmp_path).close()
        assert mode_of(tmp_path / "cache.db") == 0o600

    @pytest.mark.skipif(
        os.name == "posix" and os.geteuid() == 0, reason="root ignores file modes"
    )
    def test_read_only_database_still_degrades(self, tmp_path, caplog):
        SQLiteCache(ttl=60, cache_dir=tmp_path).close()
        (tmp_path / "cache.db").chmod(0o400)
        caplog.set_level(logging.WARNING, logger="discogs_sdk")
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        cache.set("GET:http://x/1", 200, {}, b"a")
        assert "readonly database" in caplog.text
        assert cache.get("GET:http://x/1") is None
        cache.close()
