"""TTL-based response cache with pluggable backends."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path

# Type alias for cached response tuples: (status_code, headers, body)
CacheEntry = tuple[int, dict[str, str], bytes]


class ResponseCache(ABC):
    """Abstract base for response caches.

    Subclasses implement storage; the base class owns the TTL contract.
    """

    def __init__(self, ttl: float) -> None:
        self._ttl = ttl

    @abstractmethod
    def get(self, key: str) -> CacheEntry | None:
        """Return ``(status_code, headers, body)`` if fresh, ``None`` on miss/expired."""

    @abstractmethod
    def set(self, key: str, status_code: int, headers: dict[str, str], body: bytes) -> None:
        """Store a response."""

    @abstractmethod
    def clear(self) -> None:
        """Drop all entries."""

    @abstractmethod
    def close(self) -> None:
        """Release resources. No-op if not applicable."""


class MemoryCache(ResponseCache):
    """In-memory cache using ``time.monotonic()`` (immune to clock adjustments)."""

    def __init__(self, ttl: float) -> None:
        super().__init__(ttl)
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, int, dict[str, str], bytes]] = {}

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, status, headers, body = entry
            if time.monotonic() >= expires_at:
                del self._store[key]
                return None
            return status, headers, body

    def set(self, key: str, status_code: int, headers: dict[str, str], body: bytes) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, status_code, headers, body)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def close(self) -> None:
        pass


class SQLiteCache(ResponseCache):
    """SQLite-backed cache using ``time.time()`` (survives process restarts)."""

    def __init__(self, ttl: float, cache_dir: Path) -> None:
        super().__init__(ttl)
        self._lock = threading.Lock()
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._db: sqlite3.Connection | None = sqlite3.connect(cache_dir / "cache.db", check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS cache_entries ("
            "  key TEXT PRIMARY KEY,"
            "  expires_at REAL NOT NULL,"
            "  status INTEGER NOT NULL,"
            "  headers TEXT NOT NULL,"
            "  body BLOB NOT NULL"
            ")"
        )
        self._db.commit()

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            assert self._db is not None
            row = self._db.execute(
                "SELECT expires_at, status, headers, body FROM cache_entries WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            expires_at, status, headers_json, body = row
            if time.time() >= expires_at:
                self._db.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
                self._db.commit()
                return None
            return status, json.loads(headers_json), bytes(body)

    def set(self, key: str, status_code: int, headers: dict[str, str], body: bytes) -> None:
        with self._lock:
            assert self._db is not None
            self._db.execute(
                "INSERT OR REPLACE INTO cache_entries (key, expires_at, status, headers, body) VALUES (?, ?, ?, ?, ?)",
                (key, time.time() + self._ttl, status_code, json.dumps(headers), body),
            )
            self._db.commit()

    def clear(self) -> None:
        with self._lock:
            assert self._db is not None
            self._db.execute("DELETE FROM cache_entries")
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None
