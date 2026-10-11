---
name: discogs-sdk
description: >-
  Use when Python code imports discogs_sdk (PyPI package discogs-sdk, github.com/jmfontaine/discogs-sdk), or when
  writing Python against the Discogs API with it. It is neither python3-discogs-client (import discogs_client) nor
  crate-ai/discogs-sdk; their APIs differ.
---

# discogs-sdk

Typed sync (`Discogs`) and async (`AsyncDiscogs`) clients for the Discogs API v2, built on httpx2 and Pydantic. This
skill ships inside the installed package, so it matches that version.

## Rules

1. **Identify the library first.** Look for `discogs-sdk` in `pyproject.toml` or the lockfile and for
   `import discogs_sdk`. Never mix in python3-discogs-client idioms (`discogs_client.Client`, `d.release(id)`,
   `.page(1)`, `.data`).
2. **One client per program, not per request.** `with Discogs() as client:` or `async with AsyncDiscogs() as client:`.
   Take the token from `DISCOGS_TOKEN`; never hard-code it.
3. **Lazy loading.** `.get()` sends no request. Catch `NotFoundError` around resolution (the first data access, or a
   subscription in the sync client where the model supports it), not around `.get()`. Sub-resource accessors such as
   `.rating` or `.releases` do not fetch the parent.
4. **Async.** Use `AsyncDiscogs`, `await` a proxy for its data and `async for` over pages. `await` returns a model,
   which has no sub-resources: keep the proxy for chaining.
5. **Pagination.** Paginated methods (`search()` and the `.list()` methods returning `SyncPage`/`AsyncPage`) fetch
   pages on demand. Each page starts a logical GET: a cache hit sends no network request, and retries can send
   several. Each network attempt consumes the applicable budget (60/min authenticated, 25/min anonymous). These
   methods accept `per_page`, have no `len()` or slicing, and populate `total_items`/`total_pages` from the first
   fetched response when it supplies them. `collection.folders.list()` and `collection.fields.list()` each make one
   logical GET and return a plain list. `break` early; never `list()` a large result set.
6. **Rate limits.** The SDK does not pace requests. Check `client.ratelimit is not None` before reading `.remaining`;
   the value is a pacing hint, not an atomic budget shared across concurrent work. Do not wrap reads in another retry
   layer: reads already retry.
7. **Writes.** After an ambiguous failure (a timeout, a dropped connection, a 5xx), poll for a bounded time with new
   proxies or iterators inside `client.no_cache()`: Discogs serves stale reads after a write, and a resolved proxy
   never refetches. One read missing the change does not prove failure. Do not blindly resubmit a create; report an
   outcome polling cannot establish as unknown.
8. **Caching.** Off by default (`cache=True` turns it on). `client.no_cache()` bypasses it; `client.cache_only()`
   raises `CacheMissError` instead of sending a request.
9. **Field names.** Use the Python names (`catalog_number`, `extra_artists`, `name_variation`, …); `model.raw` holds
   what Discogs sent.
10. **HTTP clients.** A custom `http_client` must be an `httpx2` client, never `httpx`; the SDK does not close it.
11. **Public API only.** Never import `discogs_sdk._*`. Never call api.discogs.com directly when an SDK method exists.

## Examples

Lazy loading, and where `NotFoundError` is raised:

```python
from discogs_sdk import Discogs, NotFoundError

with Discogs() as client:  # reads DISCOGS_TOKEN
    release = client.releases.get(352665)  # no request yet
    try:
        print(release.title)  # the GET is sent here
    except NotFoundError:
        print("No such release")
```

Async: keep the proxy to chain after awaiting it:

```python
import asyncio

from discogs_sdk import AsyncDiscogs


async def main():
    async with AsyncDiscogs() as client:
        artist_proxy = client.artists.get(3857)
        artist = await artist_proxy  # the Artist model: no .releases here
        print(artist.name)
        async for release in artist_proxy.releases.list(per_page=100):
            print(release.title)


asyncio.run(main())
```

Pagination, pacing and the field names:

```python
from discogs_sdk import Discogs

with Discogs() as client:
    for count, result in enumerate(client.search(query="Nine Inch Nails", per_page=50)):
        print(result.title, result.catalog_number)
        if count == 9:
            break  # no further page is requested
    if client.ratelimit is not None and client.ratelimit.remaining < 5:
        print("Near the rate limit; slow down")
```

Cache scopes:

```python
from discogs_sdk import CacheMissError, Discogs

with Discogs(cache=True) as client:
    with client.no_cache():
        fresh = client.releases.get(352665).title  # always reaches Discogs
    with client.cache_only():
        try:
            cached = client.releases.get(352665).title  # never reaches Discogs
        except CacheMissError:
            print("Not cached")
```

## References

Open these copies of the documentation, generated for this version, when the rules above are not enough:

- [references/migrating-from-python3-discogs-client.md](references/migrating-from-python3-discogs-client.md): the
  code imports `discogs_client`, or you are porting python3-discogs-client idioms.
- [references/endpoints.md](references/endpoints.md): you know a Discogs endpoint and need the SDK call that reaches
  it, or the reverse.
- [references/pagination.md](references/pagination.md): page cost, `per_page`, page attributes, a page that fails.
- [references/errors-and-retries.md](references/errors-and-retries.md): the exception hierarchy, what retries, and
  settling an ambiguous write.
- [references/caching.md](references/caching.md): what is cached, `no_cache()`, `cache_only()`, custom backends.
