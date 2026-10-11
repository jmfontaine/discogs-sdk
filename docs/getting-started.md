# Getting started

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
