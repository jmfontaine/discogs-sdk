"""TTL-based response cache with pluggable backends."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger("discogs_sdk")

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
    def set(
        self, key: str, status_code: int, headers: dict[str, str], body: bytes
    ) -> None:
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

    def set(
        self, key: str, status_code: int, headers: dict[str, str], body: bytes
    ) -> None:
        with self._lock:
            self._store[key] = (
                time.monotonic() + self._ttl,
                status_code,
                headers,
                body,
            )

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def close(self) -> None:
        pass


class SQLiteCache(ResponseCache):
    """SQLite-backed cache using ``time.time()`` (survives process restarts).

    The database runs in WAL mode with ``synchronous=NORMAL``, so it may create
    ``cache.db-wal`` and ``cache.db-shm`` next to ``cache.db``. A database error
    (locked, read-only, full or corrupt) is logged as a warning and never raised:
    ``get`` reports a miss, ``set`` skips the store and ``clear`` leaves the
    entries in place. Using the cache after ``close()`` raises ``RuntimeError``.
    """

    def __init__(self, ttl: float, cache_dir: Path) -> None:
        super().__init__(ttl)
        self._lock = threading.Lock()
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._path = cache_dir / "cache.db"
        db = sqlite3.connect(self._path, check_same_thread=False)
        self._db: sqlite3.Connection | None = db
        # WAL lets readers run beside a writer, and NORMAL drops the fsync on every
        # commit. Both are optimisations: on failure the SQLite defaults stay.
        try:
            mode = db.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        except sqlite3.Error as exc:
            self._warn("set PRAGMA journal_mode=WAL", exc)
        else:
            # SQLite reports a mode it cannot switch to by returning the old one.
            if str(mode).lower() != "wal":
                self._warn("set PRAGMA journal_mode=WAL", f"mode stays {mode}")
        try:
            db.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.Error as exc:
            self._warn("set PRAGMA synchronous=NORMAL", exc)
        self._table_ready = False
        try:
            self._ensure_table(db)
        except sqlite3.Error as exc:
            self._fail(db, "create the cache table", exc)

    def _require_open(self) -> sqlite3.Connection:
        # A real check, not an assert: ``python -O`` must not change the outcome.
        if self._db is None:
            raise RuntimeError("SQLiteCache is closed")
        return self._db

    def _ensure_table(self, db: sqlite3.Connection) -> None:
        # Every operation retries until it lands, so a lock another process held
        # while this one started does not disable the cache for good.
        if self._table_ready:
            return
        db.execute(
            "CREATE TABLE IF NOT EXISTS cache_entries ("
            "  key TEXT PRIMARY KEY,"
            "  expires_at REAL NOT NULL,"
            "  status INTEGER NOT NULL,"
            "  headers TEXT NOT NULL,"
            "  body BLOB NOT NULL"
            ")"
        )
        db.commit()
        self._table_ready = True

    def _warn(self, action: str, error: object) -> None:
        logger.warning("SQLite cache %s: could not %s: %s", self._path, action, error)

    def _fail(self, db: sqlite3.Connection, action: str, exc: sqlite3.Error) -> None:
        """Log a failed operation and end its transaction so no lock stays held."""
        self._warn(action, exc)
        try:
            db.rollback()
        except sqlite3.Error:  # pragma: no cover - the original error is logged
            pass

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            db = self._require_open()
            try:
                self._ensure_table(db)
                row = db.execute(
                    "SELECT expires_at, status, headers, body "
                    "FROM cache_entries WHERE key = ?",
                    (key,),
                ).fetchone()
                if row is None:
                    return None
                expires_at, status, headers_json, body = row
                if time.time() >= expires_at:
                    db.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
                    db.commit()
                    return None
            except sqlite3.Error as exc:
                self._fail(db, "read an entry", exc)
                return None
            return status, json.loads(headers_json), bytes(body)

    def set(
        self, key: str, status_code: int, headers: dict[str, str], body: bytes
    ) -> None:
        with self._lock:
            db = self._require_open()
            try:
                self._ensure_table(db)
                db.execute(
                    "INSERT OR REPLACE INTO cache_entries "
                    "(key, expires_at, status, headers, body) VALUES (?, ?, ?, ?, ?)",
                    (
                        key,
                        time.time() + self._ttl,
                        status_code,
                        json.dumps(headers),
                        body,
                    ),
                )
                db.commit()
            except sqlite3.Error as exc:
                self._fail(db, "store an entry", exc)

    def clear(self) -> None:
        with self._lock:
            db = self._require_open()
            try:
                self._ensure_table(db)
                db.execute("DELETE FROM cache_entries")
                db.commit()
            except sqlite3.Error as exc:
                self._fail(db, "clear the cache", exc)

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None
