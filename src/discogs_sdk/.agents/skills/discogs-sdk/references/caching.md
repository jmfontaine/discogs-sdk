<!-- Generated from docs/caching.md by scripts/generate_skill_refs.py for v0.8.1; do not edit. -->

# Caching

Caching is off by default. `cache=True` keeps responses in memory, or in SQLite under `cache_dir` when you give one;
`cache_ttl` sets their lifetime in seconds (default one hour). See [Configuration](https://github.com/jmfontaine/discogs-sdk/blob/v0.8.1/docs/configuration.md).

Only successful `GET`/`HEAD` responses are cached, and only once their body has parsed into the model the call
returns: a `GET` body that is not valid JSON (a gateway's HTML page, an empty body) or does not fit its model (a
release whose `id` is not a number, a page whose `results` is an object) raises its parse error and is never stored,
so a bad response fails once instead of on every read. Inventory export downloads, which are CSV, are cached as they
are.

Every cache hit is parsed again before it is returned. An entry that no longer parses, because an older SDK version
or another process sharing the SQLite file wrote it, is never served: the SDK logs a warning on the `discogs_sdk`
logger, asks the cache to delete the entry, and sends the request to the network once more, storing the new body if
it parses. Such a hit therefore costs one request, and the call's single `RequestEvent` describes that network fetch.
Inside `cache_only()` nothing is sent and the call raises `CacheMissError`.

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

The SQLite cache is opened when it is first needed, not when the client is built: constructing `Discogs(cache=True,
cache_dir=...)` or `SQLiteCache(...)` touches no file, and a read inside `no_cache()` never opens it. The first cached
read, `clear_cache()` or successful write (whose clear also runs inside `no_cache()`) creates the directory, vets
`cache.db` and connects. Concurrent first requests open it once. A request on `AsyncDiscogs` opens it on a worker
thread like every other cache lookup, while `clear_cache()` opens it on the calling thread, like the purge itself. If
the directory cannot be created, `cache.db` is refused (see below) or SQLite cannot open it, a cached read raises
`CacheError` before any network I/O, also inside `cache_only()`, and so does `clear_cache()`; the clear after a write
logs it like any failed clear. `exc.path` names `cache.db`, `exc.operation` the step (`"create the cache directory"`,
`"vet the database file"` or `"open the database"`), and `__cause__` the underlying error. The next use tries again.
Call `SQLiteCache.open()` on a cache you build yourself to run those checks up front.

Once open, the SQLite cache never fails a request. If its database is locked by another process, read-only, full or
corrupt, it logs a warning on the `discogs_sdk` logger and carries on: a lookup counts as a miss and a store is skipped,
so the response still reaches you. Using the cache after it has been closed raises `RuntimeError` (`clear_cache()`
reports it as a `CacheError` chained to it, with `path` `None`). The database runs in WAL mode, so `cache.db-wal` and
`cache.db-shm` may appear next to `cache.db`.

`client.clear_cache()` purges every entry and returns `None`. A purge you ask for is the exception to the rule
above: when the backend cannot carry it out, such as a locked or corrupt SQLite database, `clear_cache()` raises
`CacheError`, chained to the backend's error, and the entries stay as they were. `exc.path` names the database file
(`None` for a backend without one) and `exc.operation` the step that failed. The SDK never deletes or recreates the
file for you:

```python
from discogs_sdk import CacheError, Discogs

client = Discogs(cache=True)
try:
    client.clear_cache()
except CacheError as exc:
    print(f"Cache not cleared ({exc.path}): {exc.__cause__}")
```

The SQLite database holds the full bodies of your private responses (identity, orders with buyer addresses,
collection), so put `cache_dir` somewhere only you can read, such as `~/.cache/my-app`, never a shared path like
`/tmp`. A directory the cache creates is private (`0o700`) and `cache.db` is `0o600`; on POSIX, an existing `cache.db`
or sidecar that is a symlink, not a regular file, or belongs to another user is refused with `CacheError`, chained to a
`PermissionError`, when the cache opens. Entries keep only the `Content-Type`, `ETag` and
`Last-Modified` response headers.

`client.no_cache()` bypasses the cache for the current execution context. Scopes nest, the previous state is
restored even when the block raises, and each context carries its own scope, so leaving it in one thread or task
never affects another (a pool worker, or a task created before the block, does not see it; see
[Concurrency](https://github.com/jmfontaine/discogs-sdk/blob/v0.8.1/docs/concurrency.md)):

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

On `AsyncDiscogs`, both scopes are async context managers: enter them with `async with`, since a plain `with` fails.

```python
import asyncio

from discogs_sdk import AsyncDiscogs, CacheMissError


async def main():
    async with AsyncDiscogs(cache=True) as client:
        async with client.no_cache():
            release = await client.releases.get(352665)  # always hits the API
            print(release.title)
        async with client.cache_only():
            try:
                release = await client.releases.get(352665)  # never hits the API
                print(release.title)
            except CacheMissError as exc:
                print(f"Not cached: {exc.method} {exc.url}")


asyncio.run(main())
```

## Custom backends

The cache types are exported from `discogs_sdk`. To store responses elsewhere, subclass `ResponseCache` and implement
four methods: `get(key)` returns a `CacheEntry`, the `(status_code, headers, body)` tuple, or `None` on a miss or an
expired entry; `set(key, status_code, headers, body)` stores one; `clear()` drops every entry, and raises when it
cannot (`clear_cache()` passes a `CacheError` on and wraps any other exception in one); `close()` releases
whatever the backend holds. `delete(key)`, which drops one entry, is optional: the SDK calls it for a rejected entry
that no longer parses, ignores (and logs) any exception it raises, and does not rely on it, since every hit is parsed.
Its default does nothing, so such an entry stays until a fresh body overwrites it or it expires, and is rejected on
every hit until then. The base constructor takes the `ttl` in seconds, and the backend is the one that enforces
it. A backend must be thread-safe: so that disk I/O never blocks the event loop, `AsyncDiscogs` may call `get`, `set`,
`delete` and `clear` from worker threads, while `clear_cache()` and `close()` run on the calling thread, and
concurrent requests overlap. The example takes a lock for that:

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
