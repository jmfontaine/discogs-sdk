# Observability

Every live response carries Discogs' `X-Discogs-Ratelimit`, `X-Discogs-Ratelimit-Used` and
`X-Discogs-Ratelimit-Remaining` headers. `client.ratelimit` holds them as a `RateLimit(limit, used, remaining)`
parsed from the most recent **network** response: a cache hit never touches it, and a response without the headers
leaves the last known value in place. It is `None` until the first live response.

`on_request` receives exactly one `RequestEvent` per logical request, invoked synchronously before the call returns or
raises, so the event exists even when the call raises. That holds for every way a request can end once the cache, if
any, has answered; a `CacheError` from a cache that cannot be opened (see [Caching](caching.md)) ends the call before
any event. The endings are:

- a cache hit: `source="cache"`, `attempts=0`;
- a final network response, success or error status: `source="network"`, with its `status_code`;
- a transport failure (the call raises `DiscogsConnectionError`): `source="network"`, `status_code=None`,
  `error="DiscogsConnectionError"`, and `attempts` counting every attempt sent, the failed ones included;
- a request `cache_only()` refuses (the call raises `CacheMissError`): `source="miss"`, `status_code=None`,
  `attempts=0`, `error="CacheMissError"`.

Intermediate retried attempts do not emit; the one event carries `attempts`. A cache hit rejected because the entry no
longer parses (see [Caching](caching.md)) adds no event: the call's event describes how it ended, the network fetch
that replaced the entry or, inside `cache_only()`, the miss. Exceptions raised by the callback propagate unchanged;
keep it cheap and never block in it, because the async client calls it from the event loop.

| Field | Meaning |
|---|---|
| `method` | Upper-case HTTP method |
| `url` | Fully resolved URL, query string included |
| `status_code` | Status of the response that ended the call; `None` without one (a transport failure, a miss) |
| `source` | `"network"`, `"cache"` or `"miss"` |
| `elapsed_ms` | Final network attempt, or the cache lookup (`0.0` for a miss that needed no lookup) |
| `attempts` | Network attempts sent for this call, failed ones included, at most `max_retries + 1` (`1` = no retry, `4` = the default limit reached); `0` on a cache hit or a miss |
| `stored` | Whether this call wrote the response to the cache; a body the SDK parses is written only once it has parsed |
| `ratelimit` | `RateLimit` from the response; always `None` without a live response |
| `error` | Class name of the exception the call raises when there is no response (`"DiscogsConnectionError"`, `"CacheMissError"`); `None` otherwise, an error status included |

A minimal pacing loop:

```python
import time

from discogs_sdk import Discogs

client = Discogs(
    token="...", on_request=lambda e: print(e.source, e.status_code, e.elapsed_ms)
)
title = client.releases.get(352665).title  # lazy — the GET fires here
if client.ratelimit and client.ratelimit.remaining < 10:
    time.sleep(60)
```
