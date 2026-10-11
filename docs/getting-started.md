# Getting started

## Behaviors to know

Read these before writing code against the SDK; each one links to its full page.

### Lazy loading

`.get()` returns a proxy and sends no request. The first data attribute access sends the GET, and that is where
`NotFoundError` is raised; it is why the [error-handling example](errors-and-retries.md#error-handling) reads
`release.title` inside its `try`. Sub-resource accessors such as `.rating`, `.stats` or `.releases` never send a
request either. There is no public fetch method: in the sync client a data attribute access forces the fetch, and so
does subscription on a proxy whose model supports it, such as
`client.releases.get(352665).price_suggestions.get()["Mint (M)"]`.

```python
from discogs_sdk import Discogs, NotFoundError

client = Discogs()
release = client.releases.get(352665)  # no request yet
rating = release.rating  # a sub-resource accessor: still no request
try:
    print(release.title)  # the GET is sent here, and a 404 raises here
except NotFoundError:
    print("No such release")
```

### Async proxies

With `AsyncDiscogs`, `await` a proxy to fetch it and iterate pages with `async for`. Reading a data attribute on a
proxy that has not been awaited raises `AttributeError`. Awaiting returns the validated model, and the model has no
sub-resources: `artist = await client.artists.get(3857)` followed by `artist.releases` raises
`AttributeError: 'Artist' object has no attribute 'releases'`. To chain after awaiting, keep the proxy. Awaiting
resolves the kept proxy too, so its data attributes work afterwards, but it does not add sub-resources to the model.

```python
import asyncio

from discogs_sdk import AsyncDiscogs


async def main():
    async with AsyncDiscogs() as client:
        artist_proxy = client.artists.get(3857)
        artist = await artist_proxy  # the Artist model
        print(artist.name)  # "Nine Inch Nails"
        async for release in artist_proxy.releases.list(sort="year"):
            print(release.title)


asyncio.run(main())
```

### Pagination cost

Paginated methods (`search()` and the `.list()` methods returning `SyncPage`/`AsyncPage`) fetch pages on demand. Each
page starts a logical GET: a cache hit sends no network request, and retries can send several. Each network attempt
consumes the applicable budget (60/min authenticated, 25/min anonymous). These methods accept `per_page`, have no
`len()` or slicing, and populate `total_items`/`total_pages` from the first fetched response when it supplies them.
`collection.folders.list()` and `collection.fields.list()` each make one logical GET and return a plain list. See
[Pagination](pagination.md).

### Retries

Reads retry; a mutation is never replayed after an ambiguous failure, so its outcome may be unknown. See
[Errors and retries](errors-and-retries.md#rate-limits-and-retries), and
[Settling an ambiguous write](errors-and-retries.md#settling-an-ambiguous-write) for what to do then.

### Caching

Caching is off by default. Only `GET`/`HEAD` responses are cached, and a successful write clears the whole cache.
A proxy or page that has already fetched keeps its data, so fetch a new one to see a change. See
[Caching](caching.md).

## Installation

```bash
pip install discogs-sdk
# or
uv add discogs-sdk
```

Requires Python 3.10+.

## Fetching resources

Set `DISCOGS_TOKEN` to a personal access token first ([Authentication](authentication.md) covers the other modes).

```python
from discogs_sdk import Discogs

client = Discogs()  # reads DISCOGS_TOKEN from the environment

# Releases, artists, masters, labels
release = client.releases.get(352665)
print(release.title)  # lazy — HTTP fires here → "The Downward Spiral"

artist = client.artists.get(3857)
print(artist.name)  # "Nine Inch Nails"

master = client.masters.get(3719)
label = client.labels.get(647)
```

These lazy resources are read-only views: assigning to one of their attributes raises `AttributeError`, since the
value would never reach Discogs. Where the API accepts writes, they go through a resource method such as
`release.rating.update()` or `user.wantlist.update()`. Those methods take the fields Discogs documents as typed
keyword parameters: an optional field you omit, or pass as `None`, is not sent, so an update leaves it unchanged, and a
misspelled name raises `TypeError` before any request is made.

Each identifier you pass (username, order id, release id and so on) is sent as a
single, percent-encoded path segment, so a `/`, `?` or `#` in it cannot reach a
different endpoint. `"."` and `".."` raise `ValueError` before any request is made.

## Search

```python
for result in client.search(query="Pretty Hate Machine", type="release", year="1989"):
    print(f"[{result.type}] {result.title}")
    # [release] Nine Inch Nails - Pretty Hate Machine
```

## Sub-resources

```python
# Community rating
rating = client.releases.get(352665).rating.get()
print(f"Average: {rating.rating.average}")  # Average: 4.49

# Artist releases with sorting
for rel in client.artists.get(3857).releases.list(sort="year", sort_order="desc"):
    print(f"{rel.title} ({rel.year})")

# Master versions with filters
for v in client.masters.get(3719).versions.list(format="Vinyl", country="US"):
    print(f"{v.title} [{v.format}]")
```

## Async usage

```python
import asyncio
from discogs_sdk import AsyncDiscogs


async def main():
    async with AsyncDiscogs() as client:  # reads DISCOGS_TOKEN from environment
        # Must await lazy resources in async mode
        release = await client.releases.get(352665)
        print(release.title)

        # Async iteration for paginated results
        async for result in client.search(query="Nine Inch Nails"):
            print(result.title)


asyncio.run(main())
```
