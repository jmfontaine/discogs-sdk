# Observability

Every live response carries Discogs' `X-Discogs-Ratelimit`, `X-Discogs-Ratelimit-Used` and
`X-Discogs-Ratelimit-Remaining` headers. `client.ratelimit` holds them as a `RateLimit(limit, used, remaining)`
parsed from the most recent **network** response: a cache hit never touches it, and a response without the headers
leaves the last known value in place. It is `None` until the first live response.

`on_request` receives one `RequestEvent` per logical request, invoked synchronously — after a cache hit, or after the
final network response and before any error is raised, so the event exists even when the call raises. Intermediate
retried attempts do not emit; the final event carries `attempts`. A call that ends in `DiscogsConnectionError` or
`CacheMissError` emits nothing, since there is no response. Exceptions raised by the callback propagate unchanged;
keep it cheap and never block in it, because the async client calls it from the event loop.

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

from discogs_sdk import Discogs

client = Discogs(
    token="...", on_request=lambda e: print(e.source, e.status_code, e.elapsed_ms)
)
title = client.releases.get(352665).title  # lazy — the GET fires here
if client.ratelimit and client.ratelimit.remaining < 10:
    time.sleep(60)
```
