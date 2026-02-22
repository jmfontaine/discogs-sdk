"""Unit tests for cache backends (MemoryCache and SQLiteCache)."""

from __future__ import annotations

import time
from unittest.mock import patch

from discogs_sdk._cache import MemoryCache, SQLiteCache


class TestMemoryCache:
    def test_set_get_roundtrip(self):
        cache = MemoryCache(ttl=60)
        cache.set("GET:http://x/1", 200, {"content-type": "application/json"}, b'{"id":1}')
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
        cache.set("GET:http://x/1", 200, {"content-type": "application/json"}, b'{"id":1}')
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
