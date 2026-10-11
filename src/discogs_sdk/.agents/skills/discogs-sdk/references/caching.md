<!-- Generated from docs/caching.md by scripts/generate_skill_refs.py for v0.7.0; do not edit. -->

# Caching

Caching is off by default. `cache=True` keeps responses in memory, or in SQLite under `cache_dir` when you give one;
`cache_ttl` sets their lifetime in seconds (default one hour). See [Configuration](https://github.com/jmfontaine/discogs-sdk/blob/v0.7.0/docs/configuration.md).

Only successful `GET`/`HEAD` responses are cached, and a `GET` body that is not valid JSON (a gateway's HTML page, an
empty body) never is, so a bad response fails once instead of on every read; inventory export downloads, which are CSV,
are cached as they are. A body that is valid JSON but the wrong shape for its model is still cached until it expires.
Entries are keyed by method, fully resolved URL, the effective `Accept` representation, and a non-reversible digest of
the selected mode's credentials, so two clients sharing one cache — or one SQLite directory — never serve each other's
private responses, and unauthenticated traffic gets its own namespace. No token or secret is stored in a key.

Job status reads, `client.exports.get(id)` and `client.uploads.get(id)`, are never cached: each one reaches the API and
stores nothing, so a polling loop sees the job finish. A resolved proxy keeps its data, though, so poll with a new
`get()` call each time. Inside `cache_only()` these reads raise `CacheMissError`. `exports.list()`, `uploads.list()`
and `exports.download()` are cached as usual.

A successful write (`POST`, `PUT` or `DELETE` with a 2xx answer) clears the whole response cache, so no entry cached
before the write is served after it: not the written URL, not a list page, not a related folder or count. The rule
holds inside `no_cache()` too, and a cache shared between clients is cleared for all of them; entries are refetched on
demand, which costs requests. A failed write leaves the cache alone, and a cache that fails to clear is logged without
failing the write. Proxies and pages already resolved keep their in-memory data, so fetch a new proxy or iterate again
to see the change. Discogs itself may take a while to show a write, and a refetch made in that window caches what it
returned.

A write that fails ambiguously (a timeout, a dropped connection, a 5xx) leaves the cache alone too, and it may still
have taken effect. To settle it, poll for a bounded time with a new proxy or a new `.list()` iterator inside
`client.no_cache()`, so neither an earlier cache entry nor a resolved proxy answers for Discogs. One read that misses
the change does not prove a create failed; if polling cannot establish the outcome, report it as unknown rather than
resubmitting. [Settling an ambiguous write](errors-and-retries.md#settling-an-ambiguous-write) has an example.

A cache built from `cache=True` belongs to the client, and `client.close()` closes it. A `ResponseCache` instance you
pass in stays yours, like an injected `http_client`: `client.close()` never closes it, so one cache can outlive any of
the clients sharing it. Call its `close()` yourself once every client using it is done.

The built-in caches drop an expired entry when the same request looks it up again, and remove every expired entry at
least once per 100 stores; the SQLite cache also does when it opens, so `cache.db` does not carry expired rows over
from earlier runs. Entries still within `cache_ttl` stay, so the cache's size is bounded by the TTL times the rate of
new responses, not by a fixed count. Deleted rows free pages inside `cache.db` for reuse; the file itself does not
shrink.

The SQLite cache never fails a request. If its database is locked by another process, read-only, full or corrupt,
it logs a warning on the `discogs_sdk` logger and carries on: a lookup counts as a miss and a store is skipped, so the
response still reaches you. Using the cache after it has been closed raises `RuntimeError`. The database runs in WAL
mode, so `cache.db-wal` and `cache.db-shm` may appear next to `cache.db`.

The SQLite database holds the full bodies of your private responses (identity, orders with buyer addresses,
collection), so put `cache_dir` somewhere only you can read, such as `~/.cache/my-app`, never a shared path like
`/tmp`. A directory the cache creates is private (`0o700`) and `cache.db` is `0o600`; on POSIX, an existing `cache.db`
that is a symlink or belongs to another user raises `PermissionError`. Entries keep only the `Content-Type`, `ETag` and
`Last-Modified` response headers.

`client.no_cache()` bypasses the cache for the current execution context. Scopes nest, the previous state is
restored even when the block raises, and each context carries its own scope, so leaving it in one thread or task
never affects another (a pool worker, or a task created before the block, does not see it; see
[Concurrency](https://github.com/jmfontaine/discogs-sdk/blob/v0.7.0/docs/concurrency.md)):

```python
from discogs_sdk import Discogs

client = Discogs(cache=True)  # in memory; pass cache_dir=... for SQLite

with client.no_cache():
    fresh = client.releases.get(352665).title  # always hits the API
```

`client.cache_only()` is the mirror image: inside the scope a request the cache cannot serve — a miss, an expired
entry, a non-`GET`, a job status read, a disabled cache, an injected `http_client` without SDK credentials or an
enclosing `no_cache()` — raises `CacheMissError` before any network I/O. It nests and restores exactly like
`no_cache()`, so you can try everything for free first:

```python
from discogs_sdk import CacheMissError

with client.cache_only():
    try:
        title = client.releases.get(352665).title  # never hits the API
    except CacheMissError as exc:
        print(f"Not cached: {exc.method} {exc.url}")
```

## Custom backends

The cache types are exported from `discogs_sdk`. To store responses elsewhere, subclass `ResponseCache` and implement
four methods: `get(key)` returns a `CacheEntry`, the `(status_code, headers, body)` tuple, or `None` on a miss or an
expired entry; `set(key, status_code, headers, body)` stores one; `clear()` drops every entry; `close()` releases
whatever the backend holds. The base constructor takes the `ttl` in seconds, and the backend is the one that enforces
it. A backend must be thread-safe: so that disk I/O never blocks the event loop, `AsyncDiscogs` may call `get`, `set`
and `clear` from worker threads, while `clear_cache()` and `close()` run on the calling thread, and concurrent requests
overlap. The example takes a lock for that:

```python
import threading

from discogs_sdk import CacheEntry, Discogs, ResponseCache


class DictCache(ResponseCache):
    """Unbounded dict, no expiry."""

    def __init__(self) -> None:
        super().__init__(ttl=0)
        self._lock = threading.Lock()
        self._store: dict[str, CacheEntry] = {}

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            return self._store.get(key)

    def set(
        self, key: str, status_code: int, headers: dict[str, str], body: bytes
    ) -> None:
        with self._lock:
            self._store[key] = (status_code, headers, body)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def close(self) -> None:
        pass


client = Discogs(cache=DictCache())
```

`MemoryCache(ttl)` and `SQLiteCache(ttl, cache_dir)` are the backends `cache=True` builds. Create one yourself to pass
the same instance to several clients, `Discogs` and `AsyncDiscogs` alike. Clients with the same credentials share
entries; keys carry a non-reversible digest of the credentials, so clients with different ones still never see each
other's private responses. Close the cache yourself once every client using it is done:

```python
from pathlib import Path

from discogs_sdk import Discogs, SQLiteCache

shared = SQLiteCache(ttl=3600, cache_dir=Path.home() / ".cache" / "my-app")
first = Discogs(token="YOUR_TOKEN", cache=shared)
second = Discogs(token="YOUR_TOKEN", cache=shared)
print(first.releases.get(352665).title)  # fetched from the API
print(second.releases.get(352665).title)  # served from the shared cache
first.close()
second.close()
shared.close()  # a client never closes a cache passed in
```
