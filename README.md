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

Create a personal access token in [your Discogs developer settings](https://www.discogs.com/settings/developers) and
export it; the client reads it from the environment
([other auth modes](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/authentication.md)):

```bash
export DISCOGS_TOKEN="your-token-here"
```

```python
from discogs_sdk import Discogs

with Discogs() as client:
    release = client.releases.get(352665)  # no request yet
    print(release.title)  # the GET is sent here → "The Downward Spiral"

    for rel in client.artists.get(3857).releases.list(sort="year"):
        print(f"{rel.title} ({rel.year})")
```

The async client has the same API. Await a lazy resource to fetch it, and iterate pages with `async for`:

```python
import asyncio

from discogs_sdk import AsyncDiscogs


async def main():
    async with AsyncDiscogs() as client:
        release = await client.releases.get(352665)
        print(release.title)

        async for result in client.search(query="Nine Inch Nails", type="artist"):
            print(result.title)


asyncio.run(main())
```

## Behaviors to know

- **Lazy loading.** `.get()` sends no request; the first data attribute access does, and that is where
  `NotFoundError` is raised. [More](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/getting-started.md#lazy-loading)
- **Async.** `await` a proxy for its data and use `async for` on pages. Awaiting returns the model, which has no
  sub-resources, so keep the proxy to chain (`artist_proxy.releases.list()`).
  [More](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/getting-started.md#async-proxies)
- **Pagination cost.** `search()` and most `.list()` methods fetch pages on demand. Each page is a GET against the rate
  limit (60/min authenticated, 25/min anonymous); a cache hit costs nothing and retries can cost more.
  [More](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/pagination.md)
- **Retries.** Reads retry; a mutation is never replayed after an ambiguous failure.
  [More](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/errors-and-retries.md#settling-an-ambiguous-write)
- **Caching.** Off by default; only `GET`/`HEAD` are cached; a successful write clears the cache.
  [More](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/caching.md)

## Documentation

The full guide lives in [`docs/`](https://github.com/jmfontaine/discogs-sdk/tree/main/docs):

- [Getting started](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/getting-started.md) — behaviors to know, installation, fetching, search, sub-resources, async usage
- [Pagination](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/pagination.md) — what a page costs, stopping early, page attributes
- [Authentication](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/authentication.md) — personal token, consumer key/secret, OAuth 1.0a, credential precedence
- [Collection and marketplace](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/collection-and-marketplace.md) — folders, instances, wantlist, listings, orders
- [Errors and retries](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/errors-and-retries.md) — rate limits, retries, the exception hierarchy
- [Configuration](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/configuration.md) — every client parameter
- [Caching](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/caching.md) — the response cache, `no_cache()`, `cache_only()`, custom backends
- [Observability](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/observability.md) — `client.ratelimit` and `on_request` events
- [Concurrency](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/concurrency.md) — sharing a client across threads and tasks
- [Custom HTTP clients](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/http-clients.md) — injecting an `httpx2` client
- [Models](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/models.md) — field naming, timestamps, original API values

## Examples

The [`examples/`](https://github.com/jmfontaine/discogs-sdk/tree/main/examples) directory has runnable scripts for every feature:

- [`quickstart.py`](https://github.com/jmfontaine/discogs-sdk/blob/main/examples/quickstart.py) — first requests, lazy loading, search
- [`authentication.py`](https://github.com/jmfontaine/discogs-sdk/blob/main/examples/authentication.py) — all auth modes including OAuth 1.0a
- [`database.py`](https://github.com/jmfontaine/discogs-sdk/blob/main/examples/database.py) — releases, artists, masters, labels, search
- [`marketplace.py`](https://github.com/jmfontaine/discogs-sdk/blob/main/examples/marketplace.py) — listings, orders, fees, inventory
- [`collection.py`](https://github.com/jmfontaine/discogs-sdk/blob/main/examples/collection.py) — folders, instances, fields, wantlist
- [`async_usage.py`](https://github.com/jmfontaine/discogs-sdk/blob/main/examples/async_usage.py) — async client with await and async for
- [`advanced.py`](https://github.com/jmfontaine/discogs-sdk/blob/main/examples/advanced.py) — error handling, caching, custom HTTP clients, exports

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](https://github.com/jmfontaine/discogs-sdk/blob/main/CONTRIBUTING.md) for guidelines.

## License

discogs-sdk is licensed under the [Apache License 2.0](https://github.com/jmfontaine/discogs-sdk/blob/main/LICENSE.txt).
