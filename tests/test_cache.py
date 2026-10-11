"""Unit tests for cache backends (MemoryCache and SQLiteCache)."""

from __future__ import annotations

import functools
import gc
import logging
import math
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

import discogs_sdk
from discogs_sdk import CacheError, MemoryCache, SQLiteCache, _cache
from tests.conftest import exclusive_lock


class TestPublicExports:
    NAMES = ("ResponseCache", "MemoryCache", "SQLiteCache", "CacheEntry")

    def test_cache_types_are_listed_in_all(self):
        assert set(self.NAMES) <= set(discogs_sdk.__all__)

    @pytest.mark.parametrize("name", NAMES)
    def test_public_name_is_the_private_object(self, name):
        assert getattr(discogs_sdk, name) is getattr(_cache, name)


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

    def test_entry_is_fresh_before_ttl_and_expired_at_it(self):
        cache = MemoryCache(ttl=10)
        with patch("discogs_sdk._cache.time.monotonic", return_value=1000.0):
            cache.set("GET:http://x/1", 200, {}, b"ok")
        just_before = math.nextafter(1010.0, 0)
        with patch("discogs_sdk._cache.time.monotonic", return_value=just_before):
            assert cache.get("GET:http://x/1") == (200, {}, b"ok")
        with patch("discogs_sdk._cache.time.monotonic", return_value=1010.0):
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

    def test_entry_is_fresh_before_ttl_and_expired_at_it(self, tmp_path):
        cache = SQLiteCache(ttl=10, cache_dir=tmp_path)
        with patch("discogs_sdk._cache.time.time", return_value=1000.0):
            cache.set("GET:http://x/1", 200, {}, b"ok")
        just_before = math.nextafter(1010.0, 0)
        with patch("discogs_sdk._cache.time.time", return_value=just_before):
            assert cache.get("GET:http://x/1") == (200, {}, b"ok")
        with patch("discogs_sdk._cache.time.time", return_value=1010.0):
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


def _fill(cache: MemoryCache | SQLiteCache, start: int, count: int) -> None:
    for i in range(start, start + count):
        cache.set(f"GET:http://x/{i}", 200, {}, b"x")


def _row_count(cache: SQLiteCache) -> int:
    assert cache._db is not None
    return cache._db.execute("SELECT COUNT(*) FROM cache_entries").fetchone()[0]


def _entry_count(cache: MemoryCache | SQLiteCache) -> int:
    return len(cache._store) if isinstance(cache, MemoryCache) else _row_count(cache)


@contextmanager
def _clock(now: float) -> Iterator[None]:
    """Freeze both clocks the backends read: monotonic (memory) and wall (SQLite)."""
    with (
        patch("discogs_sdk._cache.time.monotonic", return_value=now),
        patch("discogs_sdk._cache.time.time", return_value=now),
    ):
        yield


@pytest.fixture(params=["memory", "sqlite"])
def make_cache(request, tmp_path):
    opened: list[MemoryCache | SQLiteCache] = []

    def make(ttl: float) -> MemoryCache | SQLiteCache:
        cache = (
            MemoryCache(ttl=ttl)
            if request.param == "memory"
            else SQLiteCache(ttl=ttl, cache_dir=tmp_path)
        )
        opened.append(cache)
        return cache

    yield make
    for cache in opened:
        cache.close()


class TestExpirySweep:
    """Expired entries nobody reads again are purged every few writes."""

    def test_unread_expired_entries_are_dropped(self, make_cache):
        cache = make_cache(ttl=10)
        with _clock(1000.0):
            _fill(cache, 0, 150)  # expire at 1010
        with _clock(1015.0):
            _fill(cache, 150, 100)
        # The sweep at the 200th write drops the first 150; the 100 entries
        # written at 1015 remain.
        assert _entry_count(cache) == 100

    def test_fresh_entry_survives_a_sweep(self, make_cache):
        cache = make_cache(ttl=10)
        with _clock(1000.0):
            _fill(cache, 0, 50)  # expire at 1010
        with _clock(1015.0):
            # These writes reach the sweep interval: the first 50 have expired,
            # these expire at 1025.
            _fill(cache, 50, _cache._SWEEP_INTERVAL - 50)
            assert _entry_count(cache) == _cache._SWEEP_INTERVAL - 50
            assert cache.get("GET:http://x/50") == (200, {}, b"x")

    def test_no_sweep_before_the_interval(self, make_cache):
        cache = make_cache(ttl=10)
        with _clock(1000.0):
            _fill(cache, 0, 10)
        with _clock(1015.0):
            _fill(cache, 10, _cache._SWEEP_INTERVAL - 11)
            assert _entry_count(cache) == _cache._SWEEP_INTERVAL - 1

    def test_reopening_purges_expired_rows(self, tmp_path):
        cache = SQLiteCache(ttl=1, cache_dir=tmp_path)
        with patch("discogs_sdk._cache.time.time", return_value=1000.0):
            _fill(cache, 0, 3)
        cache.close()
        reopened = SQLiteCache(ttl=1, cache_dir=tmp_path)
        assert _row_count(reopened) == 0
        reopened.close()

    def test_sweep_uses_the_expires_at_index(self, tmp_path):
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        assert cache._db is not None
        plan = cache._db.execute(
            f"EXPLAIN QUERY PLAN {_cache._SWEEP_SQL}", (1000.0,)
        ).fetchall()
        assert any("INDEX cache_entries_expires_at" in row[3] for row in plan), plan
        cache.close()

    def test_failed_sweep_keeps_the_store_and_logs(self, tmp_path, caplog):
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        caplog.set_level(logging.WARNING, logger="discogs_sdk")
        with patch.object(_cache, "_SWEEP_SQL", "DELETE FROM no_such_table"):
            _fill(cache, 0, _cache._SWEEP_INTERVAL)
        assert "purge expired entries" in caplog.text
        assert cache._db is not None
        assert not cache._db.in_transaction
        assert _row_count(cache) == _cache._SWEEP_INTERVAL
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
            "from discogs_sdk import SQLiteCache\n"
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
    """A failing database degrades to misses and skipped stores; ``clear`` raises."""

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

    def test_clear_while_locked_raises_and_keeps_entries(
        self, tmp_path, fast_sqlite_busy_timeout
    ):
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        cache.set("GET:http://x/1", 200, {}, b"a")
        with exclusive_lock(tmp_path), pytest.raises(CacheError) as exc_info:
            cache.clear()
        assert exc_info.value.path == tmp_path / "cache.db"
        assert exc_info.value.operation == "clear the cache"
        assert "database is locked" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, sqlite3.OperationalError)
        # The failed purge was rolled back, so this connection holds no lock.
        assert cache._db is not None
        assert not cache._db.in_transaction
        assert cache.get("GET:http://x/1") == (200, {}, b"a")
        cache.close()

    def test_garbage_file_degrades_to_misses(self, tmp_path, caplog):
        (tmp_path / "cache.db").write_bytes(b"this is not a database" * 64)
        with caplog.at_level(logging.WARNING, logger="discogs_sdk"):
            cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
            cache.set("GET:http://x/1", 200, {}, b"a")
            assert cache.get("GET:http://x/1") is None
            with pytest.raises(CacheError, match="file is not a database"):
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

    @pytest.mark.skipif(
        os.name == "posix" and os.geteuid() == 0, reason="root ignores file modes"
    )
    def test_read_only_database_without_the_index_still_serves(self, tmp_path):
        """A database written before the expires_at index existed stays readable."""
        legacy = sqlite3.connect(tmp_path / "cache.db")
        legacy.execute(
            "CREATE TABLE cache_entries (key TEXT PRIMARY KEY,"
            " expires_at REAL NOT NULL, status INTEGER NOT NULL,"
            " headers TEXT NOT NULL, body BLOB NOT NULL)"
        )
        legacy.execute(
            "INSERT INTO cache_entries VALUES (?, ?, 200, '{}', ?)",
            ("GET:http://x/1", time.time() + 600, b"a"),
        )
        legacy.commit()
        legacy.close()
        (tmp_path / "cache.db").chmod(0o400)
        cache = SQLiteCache(ttl=60, cache_dir=tmp_path)
        assert cache.get("GET:http://x/1") == (200, {}, b"a")
        cache.close()
