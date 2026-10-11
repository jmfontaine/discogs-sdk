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

from discogs_sdk._exceptions import CacheError

logger = logging.getLogger("discogs_sdk")

# Type alias for cached response tuples: (status_code, headers, body)
CacheEntry = tuple[int, dict[str, str], bytes]

# A read drops its own expired entry, but nobody may ask for a key again, so the
# built-in backends also sweep every expired entry once per this many stores.
_SWEEP_INTERVAL = 100
_SWEEP_SQL = "DELETE FROM cache_entries WHERE expires_at <= ?"

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

    The built-in backends drop an expired entry when its key is read, and also
    remove every expired entry at least once per 100 stores (``SQLiteCache``
    also does when it opens). Entries still within the TTL are kept, so their
    number is bounded by the TTL times the store rate, not by a fixed count.
    Subclasses choose their own policy: no method here requires a sweep.

    ``AsyncDiscogs`` may call ``get``, ``set`` and ``clear`` from worker threads
    (``asyncio.to_thread``) so that disk I/O never blocks the event loop, while
    ``clear_cache()`` and ``close()`` run on the calling thread, and concurrent
    requests overlap. A backend must therefore be thread-safe even when only one
    async client uses it; the built-in ones take a lock.
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
        """Drop all entries, or raise if they could not all be dropped.

        Raising is how a backend reports a failed purge: ``clear_cache()``
        re-raises a ``CacheError`` as it is and wraps any other exception in
        one, while the clear that follows a successful write logs the failure
        and returns, since the write has already happened. ``SQLiteCache``
        raises ``CacheError`` when its purge fails.
        """

    @abstractmethod
    def close(self) -> None:
        """Release resources. No-op if not applicable."""


class MemoryCache(ResponseCache):
    """In-memory cache using ``time.monotonic()`` (immune to clock adjustments)."""

    def __init__(self, ttl: float) -> None:
        super().__init__(ttl)
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, int, dict[str, str], bytes]] = {}
        self._stores = 0

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
            now = time.monotonic()
            self._store[key] = (now + self._ttl, status_code, headers, body)
            self._stores += 1
            if self._stores >= _SWEEP_INTERVAL:
                self._stores = 0
                expired = [k for k, e in self._store.items() if e[0] <= now]
                for expired_key in expired:
                    del self._store[expired_key]

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def close(self) -> None:
        pass


class SQLiteCache(ResponseCache):
    """SQLite-backed cache using ``time.time()`` (survives process restarts).

    Constructing one does no I/O. The directory is created and the database
    vetted and opened by the first ``get``, ``set`` or ``clear``, or by
    ``open()`` for a caller that wants any failure up front. Several threads
    reaching that point together open it once. A failure to create the
    directory, vet the database or connect to it raises ``CacheError`` naming
    the path and the operation, chained to the cause, and the next use tries
    again.

    The database holds private response bodies, so it is kept to the current
    user: a directory created here is ``0o700`` and ``cache.db`` is ``0o600``
    (SQLite gives its journal and WAL files the same mode). On POSIX, an existing
    ``cache.db`` or sidecar that is a symlink, not a regular file, or owned by
    someone else fails the open with ``CacheError`` chained to a
    ``PermissionError``; group or other permissions on an owned one are removed.

    The database runs in WAL mode with ``synchronous=NORMAL``, so it may create
    ``cache.db-wal`` and ``cache.db-shm`` next to ``cache.db``. Once open, a
    database error (locked, read-only, full or corrupt) in ``get`` or ``set`` is
    logged as a warning and never raised: ``get`` reports a miss and ``set``
    skips the store. ``clear`` raises ``CacheError`` instead, chained to the
    SQLite error, and leaves the entries in place. Using the cache after
    ``close()`` raises ``RuntimeError``.
    """

    def __init__(self, ttl: float, cache_dir: Path) -> None:
        super().__init__(ttl)
        self._lock = threading.Lock()
        self._dir = cache_dir
        self._path = cache_dir / "cache.db"
        self._db: sqlite3.Connection | None = None
        self._file_id: tuple[int, int] | None = None
        self._closed = False
        self._table_ready = False
        self._index_ready = False
        self._stores = 0

    def open(self) -> None:
        """Open the database now instead of at first use; a no-op once open.

        Raises:
            CacheError: The directory could not be created, or the database
                could not be vetted or opened.
            RuntimeError: The cache is closed.
        """
        with self._lock:
            self._connection()

    def _error(self, action: str, exc: Exception) -> CacheError:
        return CacheError(
            f"SQLite cache {self._path}: could not {action}: {exc}",
            operation=action,
            path=self._path,
        )

    def _connection(self) -> sqlite3.Connection:
        """Return the connection, opening it on first use. Needs ``self._lock``."""
        # A real check, not an assert: ``python -O`` must not change the outcome.
        if self._closed:
            raise RuntimeError("SQLiteCache is closed")
        if self._db is not None:
            return self._db
        try:
            _make_private_dirs(self._dir)
        except OSError as exc:
            raise self._error("create the cache directory", exc) from exc
        with _OPEN_LOCK:
            try:
                _secure_database(self._path)
                # The vetted file, which _secure_database created if missing.
                info = os.stat(self._path)
            except OSError as exc:
                raise self._error("vet the database file", exc) from exc
            try:
                db = sqlite3.connect(self._path, check_same_thread=False)
            except sqlite3.Error as exc:
                raise self._error("open the database", exc) from exc
            self._file_id = (info.st_dev, info.st_ino)
            self._db = db
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
        try:
            self._ensure_table(db)
        except sqlite3.Error as exc:
            self._fail(db, "create the cache table", exc)
        return db

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
        # Once per instance, as soon as the table is there: rows left expired by
        # earlier runs would otherwise stay until read again.
        self._sweep(db)

    def _sweep(self, db: sqlite3.Connection) -> None:
        """Delete every expired row. Needs the table and ``self._lock``."""
        try:
            # The index lets the sweep skip the fresh rows. It is made here, not
            # with the table, so a database this process cannot write, made
            # before the index existed, still serves its rows, and a lock that
            # stopped it is retried by the next sweep.
            if not self._index_ready:
                db.execute(
                    "CREATE INDEX IF NOT EXISTS cache_entries_expires_at "
                    "ON cache_entries (expires_at)"
                )
                db.commit()
                self._index_ready = True
            db.execute(_SWEEP_SQL, (time.time(),))
            db.commit()
        except sqlite3.Error as exc:
            self._fail(db, "purge expired entries", exc)

    def _warn(self, action: str, error: object) -> None:
        logger.warning("SQLite cache %s: could not %s: %s", self._path, action, error)

    def _fail(self, db: sqlite3.Connection, action: str, exc: sqlite3.Error) -> None:
        """Log a failed operation and end its transaction so no lock stays held."""
        self._warn(action, exc)
        self._rollback(db)

    @staticmethod
    def _rollback(db: sqlite3.Connection) -> None:
        try:
            db.rollback()
        except sqlite3.Error:  # pragma: no cover - the original error is reported
            pass

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            db = self._connection()
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
            db = self._connection()
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
                return
            self._stores += 1
            if self._stores >= _SWEEP_INTERVAL:
                self._stores = 0
                self._sweep(db)

    def clear(self) -> None:
        with self._lock:
            db = self._connection()
            try:
                self._ensure_table(db)
                db.execute("DELETE FROM cache_entries")
                db.commit()
            except sqlite3.Error as exc:
                # The caller asked for the purge, so its failure is raised, not
                # logged; the rollback leaves every entry in place.
                self._rollback(db)
                raise self._error("clear the cache", exc) from exc

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._db is not None:
                # Unregistered first: once the connection closes, its inode number
                # may be reused by a new file that has to be vetted.
                db, self._db = self._db, None
                db.close()
