# discogs-sdk

<p align="center">
  <a href="https://pypi.org/project/discogs-sdk/"><img src="https://img.shields.io/pypi/v/discogs-sdk.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/discogs-sdk/"><img src="https://img.shields.io/pypi/pyversions/discogs-sdk.svg" alt="Python versions"></a>
  <a href="https://github.com/jmfontaine/discogs-sdk/actions"><img src="https://github.com/jmfontaine/discogs-sdk/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/discogs-sdk/"><img src="https://img.shields.io/pypi/dm/discogs-sdk.svg" alt="PyPI downloads"></a>
  <a href="https://github.com/jmfontaine/discogs-sdk/blob/main/LICENSE.txt"><img src="https://img.shields.io/pypi/l/discogs-sdk.svg" alt="License"></a>
</p>

A typed Python client for the [Discogs API](https://www.discogs.com/developers). Sync and async, with Pydantic models, automatic pagination, and lazy resource loading.

```python
from discogs_sdk import Discogs

# Reads DISCOGS_TOKEN from environment
with Discogs() as client:
    release = client.releases.get(352665)
    print(f"{release.title} ({release.year})")
    # The Downward Spiral (1994)

    for result in client.search(query="Nine Inch Nails", type="artist"):
        print(result.title)
```

## Features

- **Sync and async** — `Discogs` for synchronous code, `AsyncDiscogs` for async/await
- **Typed models** — every response is a Pydantic v2 model with `extra="allow"` for undocumented fields
- **Lazy resources** — `.get()` returns a lightweight proxy; HTTP fires only when you access data
- **Auto-pagination** — iterate results with `for`/`async for`; pages are fetched on demand
- **Sub-resource chaining** — `client.releases.get(id).rating.get()` — intermediate accessors never trigger HTTP
- **Automatic retries** — retries on 429/5xx with exponential backoff and `Retry-After` support
- **Three auth modes** — personal token, consumer key/secret, or full OAuth 1.0a
- **Optional caching** — `cache=True` enables TTL-based response caching (in-memory or SQLite)

## Why discogs-sdk?

- **Typed models** — Pydantic v2 models give you autocomplete and IDE support instead of untyped dicts
- **Lazy loading that respects rate limits** — `.get()` returns a proxy; HTTP fires only when you access data, minimizing calls against the 60 req/min limit
- **Sync + async from one codebase** — async-first source with auto-generated sync client, identical APIs
- **Auto-pagination** — iterate results with `for`/`async for`; no manual page math
- **Modern stack** — built on httpx and Pydantic v2, not requests and raw dicts

### How it compares

| Feature | discogs-sdk | python3-discogs-client | Raw API |
|---|---|---|---|
| Typed models (Pydantic) | Yes | No | No |
| Async support | Yes | No | Manual |
| Auto-pagination | Yes | Yes | Manual |
| Lazy loading | Yes | No | N/A |
| Rate limit handling | Automatic retry | Manual | Manual |
| OAuth 1.0a | Yes | Yes | Manual |
| HTTP caching | Built-in opt-in | No | Manual |

## Installation

```bash
pip install discogs-sdk
# or
uv add discogs-sdk
```

Requires Python 3.10+.

## Quick start

### Authentication

Set your personal access token from [your Discogs developer settings](https://www.discogs.com/settings/developers) as an environment variable:

```bash
export DISCOGS_TOKEN="your-token-here"
```

```python
from discogs_sdk import Discogs

client = Discogs()  # reads DISCOGS_TOKEN from environment
```

You can also pass credentials explicitly:

```python
client = Discogs(token="your-token-here")
```

The SDK supports three auth modes: personal token, consumer key/secret, and OAuth 1.0a. All credentials resolve via constructor arg > environment variable (`DISCOGS_TOKEN`, `DISCOGS_CONSUMER_KEY`, etc.). See [`examples/authentication.py`](examples/authentication.py) for the full OAuth flow.

> [!TIP]
> Use a `.env` file with [python-dotenv](https://pypi.org/project/python-dotenv/) or
> [direnv](https://direnv.net/) to avoid exporting tokens manually in every shell.

> [!NOTE]
> Discogs enforces a 60 requests/minute rate limit. The SDK handles this automatically
> with exponential backoff and `Retry-After` support — no manual throttling needed.

### Fetching resources

```python
# Releases, artists, masters, labels
release = client.releases.get(352665)
print(release.title)  # lazy — HTTP fires here → "The Downward Spiral"

artist = client.artists.get(3857)
print(artist.name)  # "Nine Inch Nails"

master = client.masters.get(3719)
label = client.labels.get(647)
```

### Search

```python
for result in client.search(query="Pretty Hate Machine", type="release", year="1989"):
    print(f"[{result.type}] {result.title}")
    # [release] Nine Inch Nails - Pretty Hate Machine
```

### Sub-resources

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

### Async usage

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

### Marketplace

```python
# Listings
listing = client.marketplace.listings.get(123456789)
new = client.marketplace.listings.create(
    release_id=352665, condition="Very Good Plus (VG+)", price=25.00,
)
client.marketplace.listings.update(new.id, price=22.50)
client.marketplace.listings.delete(new.id)

# Orders
for order in client.marketplace.orders.list(status="Payment Received"):
    print(f"Order {order.id}: {order.status}")

# Fee lookup
fee = client.marketplace.fee.get(price=25.00, currency="USD")
```

### Collection

```python
user = client.users.get("your_username")

# Folders
folders = user.collection.folders.list()
user.collection.folders.create(name="Industrial")

# Browse folder contents
for item in user.collection.folders.get(0).releases.list(sort="added"):
    print(item.basic_information.title)

# Add a release
user.collection.folders.get(1).releases.create(release_id=352665)

# Deep chaining: folder -> release -> instance -> fields
user.collection.folders.get(1).releases.get(352665).instances.get(
    98765
).fields.update(field_id=1, value="Signed copy")

# Collection value
value = user.collection.value.get()
print(f"Median: {value.median}, Maximum: {value.maximum}")

# Wantlist
user.wantlist.create(release_id=352665, notes="Original pressing", rating=4)
for want in user.wantlist.list():
    print(want.basic_information.title)
```

### Error handling

```python
from discogs_sdk import NotFoundError, RateLimitError, AuthenticationError

try:
    release = client.releases.get(999999999)
    _ = release.title
except NotFoundError:
    print("Not found")
except RateLimitError as exc:
    print(f"Rate limited, retry after {exc.retry_after}s")
except AuthenticationError:
    print("Bad credentials")
```

The full exception hierarchy:

```
DiscogsError
+-- DiscogsConnectionError
+-- DiscogsAPIError
    +-- AuthenticationError  (401)
    +-- ForbiddenError       (403)
    +-- NotFoundError        (404)
    +-- ValidationError      (422)
    +-- RateLimitError       (429)
```

## API coverage

| Area | Resources |
|---|---|
| **Database** | Releases, Artists, Masters, Labels, Search |
| **Marketplace** | Listings, Orders, Order Messages, Fees |
| **Collection** | Folders, Releases, Instances, Custom Fields, Value |
| **User** | Profile, Identity, Wantlist, Contributions, Submissions, Inventory, Lists |
| **Inventory** | Exports (request/download CSV), Uploads (add/change/delete CSV) |
| **Lists** | Get list by ID, browse user lists |

## Examples

The [`examples/`](examples/) directory has runnable scripts for every feature:

- [`quickstart.py`](examples/quickstart.py) — first requests, lazy loading, search
- [`authentication.py`](examples/authentication.py) — all auth modes including OAuth 1.0a
- [`database.py`](examples/database.py) — releases, artists, masters, labels, search
- [`marketplace.py`](examples/marketplace.py) — listings, orders, fees, inventory
- [`collection.py`](examples/collection.py) — folders, instances, fields, wantlist
- [`async_usage.py`](examples/async_usage.py) — async client with await and async for
- [`advanced.py`](examples/advanced.py) — error handling, caching, custom HTTP clients, exports

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `token` | `None` | Personal access token |
| `consumer_key` | `None` | OAuth consumer key |
| `consumer_secret` | `None` | OAuth consumer secret |
| `access_token` | `None` | OAuth access token |
| `access_token_secret` | `None` | OAuth access token secret |
| `base_url` | `https://api.discogs.com` | API base URL |
| `timeout` | `30.0` | Request timeout in seconds |
| `max_retries` | `3` | Max retries on 429/5xx/connection errors |
| `cache` | `False` | Enable response caching |
| `cache_ttl` | `3600.0` | Cache time-to-live in seconds |
| `cache_dir` | `None` | Directory for SQLite cache; in-memory when omitted |
| `http_client` | `None` | Custom `httpx.Client` or `httpx.AsyncClient` |

Credentials are resolved in order: constructor args > environment variables.

## Field naming

Model fields use clean Python names. Where the Discogs API uses inconsistent or cryptic keys, the SDK provides a readable alias while still accepting the raw API name during deserialization:

| API field | Python attribute | Models |
|---|---|---|
| `uri150` | `uri_150` | `Image` |
| `anv` | `name_variation` | `ArtistCredit` |
| `extraartists` | `extra_artists` | `Release`, `Track` |
| `namevariations` | `name_variations` | `Artist` |
| `qty` | `quantity` | `Format` |
| `catno` | `catalog_number` | `LabelCredit`, `Company`, `LabelRelease`, `SearchResult` |
| `sublabels` | `sub_labels` | `Label` |
| `curr_abbr` | `currency_code` | `OriginalPrice`, `User` |
| `curr_id` | `currency_id` | `OriginalPrice` |
| `created_ts` | `created_at` | `Export`, `Upload`, `List_` |
| `finished_ts` | `finished_at` | `Export`, `Upload` |
| `modified_ts` | `modified_at` | `List_` |

Both names work when constructing models manually (`Image(uri150="...")` and `Image(uri_150="...")` are equivalent). When accessing attributes, use the Python name: `image.uri_150`.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

discogs-sdk is licensed under the [Apache License 2.0](LICENSE.txt).
