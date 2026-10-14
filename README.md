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

Coming from python3-discogs-client? The
[migration guide](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/migrating-from-python3-discogs-client.md)
maps each of its idioms to discogs-sdk and names the behaviour that differs.

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
- **Async.** `await` a proxy for its model, which has no sub-resources, so keep the proxy to chain and use `async for`
  on pages. [More](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/getting-started.md#async-proxies)
- **Pagination cost.** `search()` and paginated `.list()` methods fetch one page per GET as you iterate, each against
  the rate limit unless the cache serves it, so `break` once you have enough.
  [More](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/getting-started.md#pagination-cost)
- **Retries.** Reads retry on rate limits and transient failures, honouring `Retry-After` up to 60 seconds.
  [More](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/getting-started.md#retries)
- **Writes.** A mutation is never replayed after an ambiguous failure, so settle its outcome by reading, never by
  resubmitting. [More](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/getting-started.md#writes)
- **Caching.** Off by default; only `GET`/`HEAD` responses are cached, and a successful write clears the cache.
  [More](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/getting-started.md#caching)
- **Field names.** Models use Python names for cryptic API keys (`catalog_number` for `catno`), and `model.raw` keeps
  what Discogs sent. [More](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/getting-started.md#field-names)

## Design principles

The SDK does more than relay requests: it pages, retries, renames keys and parses timestamps. These rules say what it
may and may not do, and every new feature is checked against them.

- **Requests stay predictable.** A low-level method sends only the requests its documentation names. Combining calls
  is fine; the method documents the cost, and every call is observable through `on_request`. Auto-paging sends
  one GET per page as you iterate
  ([cost](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/pagination.md#what-a-page-costs)), a lazy proxy
  sends one GET on its first data access
  ([lazy loading](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/getting-started.md#lazy-loading)), and a
  retried read emits one `RequestEvent` whose `attempts` counts every send
  ([observability](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/observability.md)).
- **Data may be normalized** (names, types, timestamps, URLs) when nothing is lost, because `raw` keeps the original;
  when the result is computed from the response alone; and when the normalization is documented. Examples are
  [renamed keys](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/models.md#field-naming),
  [timestamps parsed into aware `datetime`s](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/models.md#timestamps)
  and the [absolute `uri` on search results](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/models.md#search-result-links).
  A guess the SDK cannot avoid is measured, documented and checkable through `raw`, like the
  `America/Los_Angeles` zone it assumes for a timestamp sent without an offset.
- **Data is never made up.** The SDK invents no value that the API did not send or that cannot be computed from what
  it sent, such as a guessed currency. A timestamp it cannot parse becomes `None`, not an estimate.
- **Helpers may combine calls for common use cases.** They send requests only through the SDK's public methods, so
  the cache, retries and `on_request` apply to them as to any other call.
- **Defaults are safe, sane and unsurprising.** In particular, helpers don't cap their effort by default. A caller who
  wants a bound passes one, and a capped result says whether it is complete.
- **Undocumented behaviour is quarantined.** A helper that depends on API behaviour Discogs does not document lives in
  [`discogs_sdk.experimental`](#experimental-helpers). It documents that dependency and its consequences, such as
  whether its result can be trusted to be complete; it raises when it detects that the behaviour clearly no longer
  holds; and it may change or be removed without a deprecation period. Core methods never depend on undocumented
  behaviour.

## Experimental helpers

`discogs_sdk.experimental` holds helpers that depend on API behaviour Discogs does not document, under the
[rules above](#design-principles): each may change or be removed without a deprecation period.

`releases_added_since()` answers a question the API has no filter for: which releases matching a search were added to
Discogs on or after a date. It takes a `Discogs` client; `async_releases_added_since()` takes an `AsyncDiscogs` one.

```python
from datetime import date

from discogs_sdk import Discogs
from discogs_sdk.experimental import releases_added_since

with Discogs() as client:
    result = releases_added_since(client, date(2026, 10, 1), artist="Nine Inch Nails")
    for release in result.releases:  # newest first
        print(release.date_added, release.title)
    print(result.complete)  # False only when max_requests stopped the scan
```

- **Completeness assumes an undocumented sort.** The helper searches with `sort="date_added"` and
  `sort_order="desc"`, which Discogs answers newest-added first without documenting it, and looks up each result to
  read its `date_added`, stopping at the first release added before the date. Every release it returns has a verified
  date, but a newer release that Discogs sorts after an older one is never seen. A `date_added` newer than the one
  before it shows the sort is not holding and raises `DiscogsError`.
- **Cost.** One search request per page scanned, plus one lookup per release in the window, plus one for the release
  that ends the scan (none when the results run out first). A release without a `date_added` is skipped and costs a
  lookup too. Cache hits cost nothing, and each retry is one more send.
- **No cap by default.** `max_requests=N` bounds the HTTP sends, retries included. Once the sends reach it the helper
  returns what it found with `complete=False`; a request already started may still retry, so the total can exceed `N`
  by up to `client.max_retries`.

A `date` means the start of that day in UTC; a `datetime` must be timezone-aware. `type` may only be `"release"`, and
`sort`, `sort_order` and `page` belong to the helper: passing them raises `ValueError` before any request.

## Documentation

The full guide lives in [`docs/`](https://github.com/jmfontaine/discogs-sdk/tree/main/docs):

- [Getting started](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/getting-started.md) — behaviors to know, installation, fetching resources, search, sub-resources, async usage
- [Pagination](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/pagination.md) — what a page costs, stopping early, fetching one page, page attributes
- [Authentication](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/authentication.md) — personal token, consumer key/secret, OAuth 1.0a, credential precedence
- [Collection and marketplace](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/collection-and-marketplace.md) — folders, instances, wantlist, listings, orders
- [Errors and retries](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/errors-and-retries.md) — rate limits, retries, settling an ambiguous write, the exception hierarchy
- [Configuration](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/configuration.md) — every client parameter
- [Caching](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/caching.md) — the response cache, `no_cache()`, `cache_only()`, custom backends
- [Observability](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/observability.md) — `client.ratelimit` and `on_request` events
- [Concurrency](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/concurrency.md) — sharing a client across threads and tasks
- [Custom HTTP clients](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/http-clients.md) — injecting an `httpx2` client
- [Models](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/models.md) — field naming, search result links, timestamps, original API values
- [Migrating from python3-discogs-client](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/migrating-from-python3-discogs-client.md) — idiom-by-idiom translation and behaviour differences
- [Endpoint map](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/endpoints.md) — which SDK call reaches which Discogs endpoint, with verbs, access chains and return types
- [AI coding agents](https://github.com/jmfontaine/discogs-sdk/blob/main/docs/ai-agents.md) — installing the packaged agent skill, and a rules snippet for other agents

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
