# discogs-sdk

<p align="center">
  <a href="https://pypi.org/project/discogs-sdk/"><img src="https://img.shields.io/pypi/v/discogs-sdk.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/discogs-sdk/"><img src="https://img.shields.io/pypi/pyversions/discogs-sdk.svg" alt="Python versions"></a>
  <a href="https://github.com/jmfontaine/discogs-sdk/actions"><img src="https://github.com/jmfontaine/discogs-sdk/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/discogs-sdk/"><img src="https://img.shields.io/pypi/dm/discogs-sdk.svg" alt="PyPI downloads"></a>
  <a href="https://github.com/jmfontaine/discogs-sdk/blob/main/LICENSE.txt"><img src="https://img.shields.io/pypi/l/discogs-sdk.svg" alt="License"></a>
</p>

discogs-sdk is a modern Python client for the [Discogs API](https://www.discogs.com/developers) with full endpoint coverage, a fluent chainable syntax, and built-in response caching.

```python
from discogs_sdk import Discogs

with Discogs() as client:
    release = client.releases.get(352665)
    print(f"{release.title} ({release.year})")

    for result in client.search(query="Nine Inch Nails", type="artist"):
        print(result.title)
```

## Installation

```bash
pip install discogs-sdk
# or
uv add discogs-sdk
```

Requires Python 3.10+.

## Features

- **Full API Coverage** — Every endpoint in the Discogs API v2
- **Fluent API** — Chain sub-resources naturally: `client.releases.get(id).rating.get()`
- **Lazy Loading** — No HTTP calls until you actually need the data
- **Effortless Pagination** — Browse results without managing pages or offsets
- **Rate Limit Friendly** — Automatically stay within API limits
- **Built-in Caching** — Optional TTL-based caching reduces API calls
- **Flexible Auth** — Supports personal tokens, consumer key/secret, or full OAuth 1.0a
- **Type Safe** — Get autocomplete and IDE support
- **Async & Sync** — Full support for both synchronous and asynchronous workflows

### How it compares

| | discogs-sdk | python3-discogs-client |
|---|---|---|
| Full API coverage | ✓ | Partial |
| Fluent sub-resource chaining | ✓ | ✗ |
| Lazy loading | ✓ | ✗ |
| Auto-pagination | ✓ | ✓ |
| Automatic rate limit handling | ✓ | ✗ |
| Caching | ✓ | ✗ |
| OAuth 1.0a | ✓ | ✓ |
| Type safe (Pydantic models) | ✓ | ✗ |
| Async & sync | ✓ | ✗ |

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

The SDK supports three auth modes: personal token, consumer key/secret, and OAuth 1.0a. Credentials passed to the constructor take precedence over environment variables (`DISCOGS_TOKEN`, `DISCOGS_CONSUMER_KEY`, etc.). See [`examples/authentication.py`](examples/authentication.py) for the full OAuth flow.

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
├── DiscogsConnectionError
└── DiscogsAPIError
    ├── AuthenticationError  (401)
    ├── ForbiddenError       (403)
    ├── NotFoundError        (404)
    ├── ValidationError      (422)
    └── RateLimitError       (429)
```

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
| `access_token_secret` | `None` | OAuth access token secret |
| `access_token` | `None` | OAuth access token |
| `base_url` | `https://api.discogs.com` | API base URL |
| `cache_dir` | `None` | Directory for SQLite cache; in-memory when omitted |
| `cache_ttl` | `3600.0` | Cache time-to-live in seconds |
| `cache` | `False` | Enable response caching, or pass a custom `ResponseCache` instance |
| `consumer_key` | `None` | OAuth consumer key |
| `consumer_secret` | `None` | OAuth consumer secret |
| `http_client` | `None` | Custom `httpx.Client` or `httpx.AsyncClient` |
| `max_retries` | `3` | Max retries on 429/5xx/connection errors |
| `timeout` | `30.0` | Request timeout in seconds |
| `token` | `None` | Personal access token |

Credentials are resolved in order: constructor args > environment variables.

## Field naming

Model fields use clean Python names. Where the Discogs API uses inconsistent or cryptic keys, the SDK provides a readable alias while still accepting the raw API name during deserialization:

| API field | Python attribute | Models |
|---|---|---|
| `anv` | `name_variation` | `ArtistCredit` |
| `catno` | `catalog_number` | `LabelCredit`, `Company`, `LabelRelease`, `SearchResult` |
| `created_ts` | `created_at` | `Export`, `Upload`, `List_` |
| `curr_abbr` | `currency_code` | `OriginalPrice`, `User` |
| `curr_id` | `currency_id` | `OriginalPrice` |
| `extraartists` | `extra_artists` | `Release`, `Track` |
| `finished_ts` | `finished_at` | `Export`, `Upload` |
| `modified_ts` | `modified_at` | `List_` |
| `namevariations` | `name_variations` | `Artist` |
| `qty` | `quantity` | `Format` |
| `sublabels` | `sub_labels` | `Label` |
| `uri150` | `uri_150` | `Image` |

Both names work as attributes, so you can use whichever you prefer:

```python
release = client.releases.get(352665)  # The Downward Spiral
print(release.extra_artists)  # Python name
print(release.extraartists)   # API name — same value
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

discogs-sdk is licensed under the [Apache License 2.0](LICENSE.txt).
