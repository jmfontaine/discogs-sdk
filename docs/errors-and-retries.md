# Errors and retries

## Rate limits and retries

> [!NOTE]
> Discogs allows 60 requests/minute authenticated and 25/minute unauthenticated, measured as a moving average over
> the last 60 seconds. The SDK does not pace your requests: it retries a rate-limited **read** a bounded number of
> times (`max_retries`, default 3), honouring `Retry-After` (seconds or an HTTP-date) up to 60 seconds. A longer
> `Retry-After` is not slept through: the error is raised immediately and you decide whether to wait.
> `RateLimitError.retry_after` carries the raw header value and `retry_after_seconds` the delay it asks for, parsed
> the way the SDK parses it (decimal seconds or an HTTP-date, measured when the error is raised; `None` when the header
> is missing or unusable). Sustained traffic above the limit still needs pacing on your side, and you can still receive
> `RateLimitError` once the retries are exhausted.

> [!WARNING]
> Mutations are not replayed. A `POST`, `PUT` or `DELETE` is retried only when the failure proves the request never
> reached the server, such as a refused connection. After a read timeout, a dropped connection or a 5xx the change may
> already have been committed, so the SDK raises instead of sending it again — the remote outcome is genuinely unknown
> and only you can decide how to reconcile it.

Every transport failure surfaces as `DiscogsConnectionError`, chained to the underlying `httpx2` error
(`exc.__cause__`). Reads retry the transient ones: network errors, timeouts, and a keep-alive connection the server
closed (`RemoteProtocolError`). Failures that would repeat identically — `LocalProtocolError`, `UnsupportedProtocol`,
`ProxyError`, `DecodingError`, `TooManyRedirects` — are raised at once for every method. `exc.transient` records that
classification, so you can tell "try again later" from "fix your setup" without importing `httpx2`: it is `True`
exactly when a read failing the same way would be retried, even if the failed request was a mutation the SDK did not
replay.

`max_retries=N` allows up to N + 1 attempts: the first request plus N retries, so the default 3 means up to 4
requests for one call. A read is retried on 429, 500, 502, 503 and 504 and on the transient transport failures above.
Fewer attempts are sent when:

- the failure is not retryable: any other status, or a transport failure that would repeat identically;
- the request is a mutation and the failure may have reached the server (see the warning above);
- a `Retry-After` exceeds 60 seconds, which raises at once.

Before each retry the SDK sleeps for the response's `Retry-After` when it carries a usable one: a finite,
non-negative number of seconds or an HTTP-date. Otherwise, after a transport failure or a response without a usable
`Retry-After`, it backs off exponentially: `min(2**attempt, 60) + random.random()` seconds, where `attempt` is the
zero-based index of the attempt that just failed. The default three retries therefore wait 1, 2 and 4 seconds, each
plus up to one second of random jitter.

The `attempts` field of [`RequestEvent`](observability.md) reports how many were sent.

## Settling an ambiguous write

When a `POST`, `PUT` or `DELETE` fails with `DiscogsConnectionError` (a timeout, a dropped connection) or a 5xx, the
change may or may not have been made, and the SDK will not send it again. Settle the outcome by reading, not by
resubmitting:

- Poll for a bounded time, each time with a new proxy or a new `.list()` iterator inside `client.no_cache()`. A
  proxy that already fetched never refetches, and outside `no_cache()` a read may be served from the cache.
- Discogs serves stale reads after a write: a change has taken from 17 to 37 seconds to appear. One read that does not
  show the change does not prove the write failed.
- If polling cannot establish the outcome, report it as unknown. Resubmitting a create blindly can make a duplicate.

The SDK has no automatic reconciliation. A sketch for a want:

```python
import time

from discogs_sdk import Discogs, DiscogsAPIError, DiscogsConnectionError

client = Discogs()
user = client.users.get(client.user.identity().username)


def want_listed(release_id: int) -> bool:
    with client.no_cache():  # a new iterator, every page from Discogs
        return any(want.id == release_id for want in user.wantlist.list())


ambiguous = False
try:
    user.wantlist.create(release_id=352665)
except DiscogsConnectionError:
    ambiguous = True  # timed out or dropped: the PUT may have landed
except DiscogsAPIError as exc:
    if exc.status_code < 500:
        raise  # a 4xx is a definite refusal
    ambiguous = True

if ambiguous:
    deadline = time.monotonic() + 120
    while not want_listed(352665):
        if time.monotonic() > deadline:
            print("Unknown whether the want was added; check again later")
            break
        time.sleep(10)
```

Each poll here pages through the whole wantlist, so keep the interval wide on a large one.

## Error handling

```python
from discogs_sdk import AuthenticationError, Discogs, NotFoundError, RateLimitError

client = Discogs()

try:
    release = client.releases.get(999999999)
    _ = release.title
except NotFoundError as exc:
    print(f"Not found: {exc.method} {exc.url}")
except RateLimitError as exc:
    if exc.retry_after_seconds is not None:  # parsed Retry-After; .retry_after is raw
        print(f"Rate limited, retry after {exc.retry_after_seconds:g}s")
    if exc.ratelimit:  # the 429's own X-Discogs-Ratelimit* headers, when present
        print(f"{exc.ratelimit.used}/{exc.ratelimit.limit} used this window")
except AuthenticationError:
    print("Bad credentials")
```

Every `DiscogsAPIError` names the request that failed: `exc.method` (upper-case) and
`exc.url` (fully resolved, query string included, as in `RequestEvent.url`), so an
error raised while iterating a listing points at the page that failed. `exc.ratelimit`
holds the `RateLimit` from the failing response's `X-Discogs-Ratelimit*` headers for
any status, or `None` when they are missing. All three are `None` on an exception you
construct yourself without them.

The full exception hierarchy:

```
DiscogsError
├── DiscogsConnectionError
├── CacheMissError
├── CacheError
└── DiscogsAPIError
    ├── AuthenticationError  (401)
    ├── ForbiddenError       (403)
    ├── NotFoundError        (404)
    ├── ValidationError      (422)
    └── RateLimitError       (429)
```

The OAuth helpers in `discogs_sdk.oauth` (`get_request_token`, `get_access_token`
and their `async_` variants) raise from the same hierarchy: an error status maps as
above (401 → `AuthenticationError`, 400 → `DiscogsAPIError`, …), a transport failure
raises `DiscogsConnectionError`, and a successful response missing either
`oauth_token` or `oauth_token_secret` raises `DiscogsAPIError` naming any
`oauth_problem`. They never retry: the access-token exchange is sent at most once.

`client.exports.request()` and `client.uploads.create()`, `change()` and `delete()`
return the new job's id, read from the `Location` header of the response, for
`exports.get()`, `exports.download()` and `uploads.get()`. A successful response
whose `Location` is missing or does not end in an integer raises `DiscogsAPIError`
with that 2xx status: Discogs accepted the request, so the job probably exists. Find
it with `exports.list()` or `uploads.list()` instead of submitting again.

`str(exc)` on a `DiscogsAPIError` is a short summary, `"<status>: <message>"`. The
message is the body's `message` when that is a non-empty string, otherwise the body
itself, cut to 500 characters so a gateway error page does not flood logs; the errors
above that the SDK raises on a 2xx describe the problem instead. The full payload
stays in `exc.response_body`.

Every SDK exception survives `pickle`, `copy.copy` and `copy.deepcopy` with its
attributes (`status_code`, `response_body`, `retry_after`, `retry_after_seconds`,
`ratelimit`, `method`, `url`, `transient`, `operation`, `path`) and any notes, so an error
raised in a `ProcessPoolExecutor` or `multiprocessing` worker reaches the parent as the
same class. As with any pickled exception, `__cause__`, `__context__` and the traceback
are not carried over. `retry_after_seconds` keeps the value computed when the error was
raised.

A paginated iterator that raises keeps its place, and a page with the wrong shape raises `DiscogsError`; see
[When a page fails](pagination.md#when-a-page-fails).

### Exceptions outside `DiscogsError`

Apart from the `ValueError`s that reject invalid arguments, such as incomplete
credentials, the SDK lets three exceptions through on purpose, and
`except DiscogsError` catches none of them:

- `json.JSONDecodeError` (a `ValueError`) when a 2xx response that the SDK reads as
  JSON has a body that is not JSON; a body that is not even UTF-8 raises
  `UnicodeDecodeError`, also a `ValueError`. Error statuses are mapped before the
  endpoint parses the body, and a success is not an API error, so the SDK raises the
  parse failure instead of a fallback value.
- `pydantic.ValidationError` (a `ValueError`) when a 2xx JSON body does not fit the
  model, such as a release whose `id` is not a number. The response was a success,
  so this is a parsing failure rather than an API error. Only a list page's envelope
  is checked by the SDK itself (see [Pagination](pagination.md#when-a-page-fails)); its
  items go to Pydantic like any other model.
- `FileNotFoundError` (an `OSError`) from `client.uploads.create()`, `change()` or
  `delete()` when `file` names a path that does not exist. The file is read before
  any request is sent, so there is no response to map.

Transport failures are not among them: they surface as `DiscogsConnectionError`, as
described under [Rate limits and retries](#rate-limits-and-retries).

Two unrelated classes are named `ValidationError`. `discogs_sdk.ValidationError` is
the HTTP 422 `DiscogsAPIError` above and is not a `ValueError`;
`pydantic.ValidationError` is the model parsing failure. Imported under the same
name, one silently shadows the other, so alias them:

```python
from discogs_sdk import ValidationError as ApiValidationError
from pydantic import ValidationError as ModelValidationError
```
