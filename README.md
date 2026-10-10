# discogs-sdk

<p align="center">
  <a href="https://pypi.org/project/discogs-sdk/"><img src="https://img.shields.io/pypi/v/discogs-sdk.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/discogs-sdk/"><img src="https://img.shields.io/pypi/pyversions/discogs-sdk.svg" alt="Python versions"></a>
  <a href="https://github.com/jmfontaine/discogs-sdk/actions"><img src="https://github.com/jmfontaine/discogs-sdk/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/discogs-sdk/"><img src="https://img.shields.io/pypi/dm/discogs-sdk.svg" alt="PyPI downloads"></a>
  <a href="https://github.com/jmfontaine/discogs-sdk/blob/main/LICENSE.txt"><img src="https://img.shields.io/pypi/l/discogs-sdk.svg" alt="License"></a>
</p>

discogs-sdk is a modern Python client for the [Discogs API](https://www.discogs.com/developers) covering every documented v2 endpoint, with a fluent chainable syntax and built-in response caching.

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

- **Complete Endpoint Coverage** — Every route in the Discogs API v2 documentation
- **Fluent API** — Chain sub-resources naturally: `client.releases.get(id).rating.get()`
- **Lazy Loading** — No HTTP calls until you actually need the data
- **Effortless Pagination** — Browse results without managing pages or offsets
- **Rate Limit Aware** — Bounded retries with `Retry-After` support, the live budget on `client.ratelimit`, and a structured event per request
- **Built-in Caching** — Optional TTL-based caching reduces API calls
- **Flexible Auth** — Supports personal tokens, consumer key/secret, or full OAuth 1.0a
- **Type Safe** — Get autocomplete and IDE support
- **Async & Sync** — Full support for both synchronous and asynchronous workflows

### How it compares

The established alternative is [python3-discogs-client](https://github.com/joalla/discogs_client). Both load data
lazily, paginate automatically, support OAuth 1.0a and back off on HTTP 429, so the differences that matter are:

| | discogs-sdk | python3-discogs-client |
|---|---|---|
| Documented v2 API coverage | Complete | Partial † |
| Sync and async | Both | Sync only |
| Responses | Typed Pydantic models | Untyped attributes |
| Response cache | In-memory or SQLite | None |

† No inventory export or upload, release ratings or have/want stats, collection fields, folder creation,
contributions or submissions.

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

The SDK supports three auth modes: personal token, consumer key/secret, and OAuth 1.0a. Exactly one mode is selected
when the client is constructed, and only that mode's credentials are used. The precedence is:

1. An explicit `token` selects personal-token auth and overrides every environment credential.
2. Explicit OAuth access-token credentials select OAuth; any missing half may come from the matching `DISCOGS_*`
   variable, but an unrelated environment token never takes over.
3. Explicit `consumer_key`/`consumer_secret` select consumer auth, without borrowing environment access tokens.
4. With no auth arguments, the environment resolves the mode: `DISCOGS_TOKEN`, then a complete OAuth set, then
   `DISCOGS_CONSUMER_KEY`/`DISCOGS_CONSUMER_SECRET`, then unauthenticated.

An explicitly selected but incomplete credential set raises `ValueError` rather than quietly falling back to a
different account or mode. See [`examples/authentication.py`](examples/authentication.py) for the full OAuth flow.

> [!TIP]
> Use a `.env` file with [python-dotenv](https://pypi.org/project/python-dotenv/) or
> [direnv](https://direnv.net/) to avoid exporting tokens manually in every shell.

> [!NOTE]
> Discogs allows 60 requests/minute authenticated and 25/minute unauthenticated, measured as a moving average over
> the last 60 seconds. The SDK does not pace your requests: it retries a rate-limited **read** a bounded number of
> times (`max_retries`, default 3), honouring `Retry-After`. Sustained traffic above the limit still needs pacing on
> your side, and you can still receive `RateLimitError` once the retries are exhausted.

> [!WARNING]
> Mutations are not replayed. A `POST`, `PUT` or `DELETE` is retried only when the failure proves the request never
> reached the server, such as a refused connection. After a read timeout, a dropped connection or a 5xx the change may
> already have been committed, so the SDK raises instead of sending it again — the remote outcome is genuinely unknown
> and only you can decide how to reconcile it.

Every transport failure surfaces as `DiscogsConnectionError`, chained to the underlying `httpx2` error
(`exc.__cause__`). Reads retry the transient ones: network errors, timeouts, and a keep-alive connection the server
closed (`RemoteProtocolError`). Failures that would repeat identically — `LocalProtocolError`, `UnsupportedProtocol`,
`ProxyError`, `DecodingError`, `TooManyRedirects` — are raised at once for every method.

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

# Add a release. The response identifies the copy you just created, which is
# how you tell it apart from copies of the same release you already own.
created = user.collection.folders.get(1).releases.create(release_id=352665)

# Deep chaining: folder -> release -> instance -> fields
instances = user.collection.folders.get(1).releases.get(352665).instances
instances.get(created.instance_id).fields.update(field_id=1, value="Signed copy")

# Collection value
value = user.collection.value.get()
print(f"Median: {value.median}, Maximum: {value.maximum}")

# Wantlist — the add takes only the release id; Discogs drops notes and ratings
# sent to it, so they go in the update call
user.wantlist.create(release_id=352665)
user.wantlist.update(352665, notes="Original pressing", rating=4)
for want in user.wantlist.list():
    print(want.basic_information.title)
```

### Marketplace

```python
# Listings
listing = client.marketplace.listings.get(123456789)
new = client.marketplace.listings.create(
    release_id=352665,
    condition="Very Good Plus (VG+)",
    price=25.00,
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
    if exc.ratelimit:  # the 429's own X-Discogs-Ratelimit* headers, when present
        print(f"{exc.ratelimit.used}/{exc.ratelimit.limit} used this window")
except AuthenticationError:
    print("Bad credentials")
```

The full exception hierarchy:

```
DiscogsError
├── DiscogsConnectionError
├── CacheMissError
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
| `cache` | `False` | Enable response caching, or pass a custom `ResponseCache` instance; an injected instance is never closed by the client |
| `consumer_key` | `None` | OAuth consumer key |
| `consumer_secret` | `None` | OAuth consumer secret |
| `http_client` | `None` | Custom `httpx2.Client` or `httpx2.AsyncClient` |
| `max_retries` | `3` | Max retries; reads retry on 429/5xx, network errors, timeouts and dropped connections, mutations only on pre-send failures |
| `on_request` | `None` | Callback receiving a `RequestEvent` per request |
| `timeout` | `30.0` | Request timeout in seconds |
| `token` | `None` | Personal access token |

See [Authentication](#authentication) for how a credential mode is selected.

### Caching

Only successful `GET`/`HEAD` responses are cached. Entries are keyed by method, fully resolved URL, the effective
`Accept` representation, and a non-reversible digest of the selected mode's credentials, so two clients sharing one
cache — or one SQLite directory — never serve each other's private responses, and unauthenticated traffic gets its
own namespace. No token or secret is stored in a key.

A cache built from `cache=True` belongs to the client, and `client.close()` closes it. A `ResponseCache` instance you
pass in stays yours, like an injected `http_client`: `client.close()` never closes it, so one cache can outlive any of
the clients sharing it. Call its `close()` yourself once every client using it is done.

`client.no_cache()` bypasses the cache for the current execution context. Scopes nest, the previous state is
restored even when the block raises, and concurrent tasks or threads each carry their own state:

```python
with client.no_cache():
    fresh = client.releases.get(352665).title  # always hits the API
```

`client.cache_only()` is the mirror image: inside the scope a request the cache cannot serve — a miss, an expired
entry, a non-`GET`, a disabled cache or an enclosing `no_cache()` — raises `CacheMissError` before any network I/O.
It nests and restores exactly like `no_cache()`, so you can try everything for free first:

```python
from discogs_sdk import CacheMissError

with client.cache_only():
    try:
        title = client.releases.get(352665).title  # never hits the API
    except CacheMissError as exc:
        print(f"Not cached: {exc.method} {exc.url}")
```

### Observability

Every live response carries Discogs' `X-Discogs-Ratelimit`, `X-Discogs-Ratelimit-Used` and
`X-Discogs-Ratelimit-Remaining` headers. `client.ratelimit` holds them as a `RateLimit(limit, used, remaining)`
parsed from the most recent **network** response: a cache hit never touches it, and a response without the headers
leaves the last known value in place. It is `None` until the first live response.

`on_request` receives one `RequestEvent` per logical request, invoked synchronously — after a cache hit, or after the
final network response and before any error is raised, so the event exists even when the call raises. Intermediate
retried attempts do not emit; the final event carries `attempts`. A call that ends in `DiscogsConnectionError` emits
nothing, since there is no response. Exceptions raised by the callback propagate unchanged; keep it cheap and never
block in it, because the async client calls it from the event loop.

| Field | Meaning |
|---|---|
| `method` | Upper-case HTTP method |
| `url` | Fully resolved URL, query string included |
| `status_code` | Status of the response that ended the call |
| `source` | `"network"` or `"cache"` |
| `elapsed_ms` | Final network attempt, or the cache lookup |
| `attempts` | Network attempts (`1` = no retry); `0` on a cache hit |
| `stored` | Whether this call wrote the response to the cache |
| `ratelimit` | `RateLimit` from the response; always `None` on a cache hit |

A minimal pacing loop:

```python
import time

client = Discogs(
    token="...", on_request=lambda e: print(e.source, e.status_code, e.elapsed_ms)
)
title = client.releases.get(352665).title  # lazy — the GET fires here
if client.ratelimit and client.ratelimit.remaining < 10:
    time.sleep(60)
```

### Custom HTTP clients

An injected `http_client` must be an `httpx2` client — the SDK is built on [httpx2](https://github.com/pydantic/httpx2),
Pydantic's maintained continuation of httpx. It owns its transport configuration and its lifecycle: `client.close()`
never closes it. SDK credentials, User-Agent and media type are still applied per request, so they describe the request
without mutating your client's defaults, and its own `httpx2.Auth` cannot replace credentials you gave the SDK. When the
SDK has no credentials of its own, your client's authentication is preserved and its responses are not cached, because
the SDK cannot tell whose account they belong to.

## Field naming

Model fields use clean Python names. Where the Discogs API uses inconsistent or cryptic keys, the SDK provides a readable alias while still accepting the raw API name during deserialization:

| API field | Python attribute | Models |
|---|---|---|
| `anv` | `name_variation` | `ArtistCredit` |
| `catno` | `catalog_number` | `LabelCredit`, `Company`, `LabelRelease`, `MasterVersion`, `SearchResult` |
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
print(release.extraartists)  # API name — same value
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

discogs-sdk is licensed under the [Apache License 2.0](LICENSE.txt).
