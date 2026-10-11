"""TTL-based response cache with pluggable backends."""

from __future__ import annotations

import errno
import json
import logging
import os
import sqlite3
import stat
import threading
import time
import weakref
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger("discogs_sdk")

# Type alias for cached response tuples: (status_code, headers, body)
CacheEntry = tuple[int, dict[str, str], bytes]

# Files SQLite keeps next to the database: the rollback journal and the WAL pair.
_SIDECAR_SUFFIXES = ("-journal", "-wal", "-shm")
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
# Closing any descriptor of a file drops every POSIX lock this process holds on
# it, SQLite's included. A database an open SQLiteCache in this process uses was
# vetted when that cache opened it, so it is not reopened for vetting. Sqlite3
# connections opened outside SQLiteCache are invisible here. _OPEN_LOCK covers
# the lookup, the vetting and the connect; nothing on a GC path takes it.
_OPEN_CACHES: weakref.WeakSet[SQLiteCache] = weakref.WeakSet()
_OPEN_LOCK = threading.Lock()


def _make_private_dirs(path: Path) -> None:
    """Create *path* and its missing parents as ``0o700``; leave existing ones be."""
    missing: list[Path] = []
    # An anchor is its own parent; one that does not exist fails in mkdir below.
    while not path.exists() and path.parent != path:
        missing.append(path)
        path = path.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700, exist_ok=True)


def _open_nofollow(path: Path, *, create: bool) -> int:
    """Open *path* without following a symlink, creating it ``0o600`` if asked.

    A file this process may only read is opened read-only instead, so it still
    reaches SQLite, whose read-only errors the cache degrades on.
    """
    flags = os.O_RDWR | _NOFOLLOW | (os.O_CREAT if create else 0)
    try:
        return os.open(path, flags, 0o600)
    except OSError as exc:
        # O_NOFOLLOW reports a symlink as ELOOP (EMLINK on FreeBSD).
        if exc.errno in (errno.ELOOP, errno.EMLINK, errno.EISDIR):
            raise _not_private(path) from exc
        if exc.errno not in (errno.EACCES, errno.EPERM, errno.EROFS):
            raise
        # O_NONBLOCK keeps a FIFO from blocking until a writer appears.
        nonblock = getattr(os, "O_NONBLOCK", 0)
        return os.open(path, os.O_RDONLY | nonblock | _NOFOLLOW)


def _not_private(path: Path) -> PermissionError:
    return PermissionError(f"{path} is not a regular file owned by the current user")


def _vet(fd: int, path: Path) -> None:
    """Refuse anything but a regular file the current user owns; make it 0o600."""
    if os.name != "posix":  # pragma: no cover - Windows has no POSIX modes
        return
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
        raise _not_private(path)
    if info.st_mode & 0o077:
        os.fchmod(fd, 0o600)


def _secure_database(path: Path) -> None:
    """Create or vet *path* and vet its sidecars, unless this process has it open.

    Call with ``_OPEN_LOCK`` held.
    """
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        pass
    else:
        file_id = (info.st_dev, info.st_ino)
        if any(c._db is not None and c._file_id == file_id for c in _OPEN_CACHES):
            return
    for candidate, create in [
        (path, True),
        *((path.with_name(path.name + s), False) for s in _SIDECAR_SUFFIXES),
    ]:
        try:
            fd = _open_nofollow(candidate, create=create)
        except FileNotFoundError:
            continue
        try:
            _vet(fd, candidate)
        finally:
            os.close(fd)


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

    The database holds private response bodies, so it is kept to the current
    user: a directory created here is ``0o700`` and ``cache.db`` is ``0o600``
    (SQLite gives its journal and WAL files the same mode). On POSIX, an existing
    ``cache.db`` or sidecar that is a symlink, not a regular file, or owned by
    someone else raises ``PermissionError``; group or other permissions on an
    owned one are removed.

    The database runs in WAL mode with ``synchronous=NORMAL``, so it may create
    ``cache.db-wal`` and ``cache.db-shm`` next to ``cache.db``. A database error
    (locked, read-only, full or corrupt) is logged as a warning and never raised:
    ``get`` reports a miss, ``set`` skips the store and ``clear`` leaves the
    entries in place. Using the cache after ``close()`` raises ``RuntimeError``.
    """

    def __init__(self, ttl: float, cache_dir: Path) -> None:
        super().__init__(ttl)
        self._lock = threading.Lock()
        _make_private_dirs(cache_dir)
        self._path = cache_dir / "cache.db"
        with _OPEN_LOCK:
            _secure_database(self._path)
            db = sqlite3.connect(self._path, check_same_thread=False)
            info = os.stat(self._path)
            self._file_id = (info.st_dev, info.st_ino)
            self._db: sqlite3.Connection | None = db
            _OPEN_CACHES.add(self)
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
                # Unregistered first: once the connection closes, its inode number
                # may be reused by a new file that has to be vetted.
                db, self._db = self._db, None
                db.close()
