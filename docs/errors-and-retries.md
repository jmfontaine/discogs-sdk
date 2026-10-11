# Errors and retries

## Rate limits and retries

> [!NOTE]
> Discogs allows 60 requests/minute authenticated and 25/minute unauthenticated, measured as a moving average over
> the last 60 seconds. The SDK does not pace your requests: it retries a rate-limited **read** a bounded number of
> times (`max_retries`, default 3), honouring `Retry-After` (seconds or an HTTP-date) up to 60 seconds. A longer
> `Retry-After` is not slept through: the error is raised immediately, `RateLimitError.retry_after` carries the raw
> value, and you decide whether to wait. Sustained traffic above the limit still needs pacing on your side, and you can
> still receive `RateLimitError` once the retries are exhausted.

> [!WARNING]
> Mutations are not replayed. A `POST`, `PUT` or `DELETE` is retried only when the failure proves the request never
> reached the server, such as a refused connection. After a read timeout, a dropped connection or a 5xx the change may
> already have been committed, so the SDK raises instead of sending it again — the remote outcome is genuinely unknown
> and only you can decide how to reconcile it.

Every transport failure surfaces as `DiscogsConnectionError`, chained to the underlying `httpx2` error
(`exc.__cause__`). Reads retry the transient ones: network errors, timeouts, and a keep-alive connection the server
closed (`RemoteProtocolError`). Failures that would repeat identically — `LocalProtocolError`, `UnsupportedProtocol`,
`ProxyError`, `DecodingError`, `TooManyRedirects` — are raised at once for every method.

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
    print(f"Rate limited, retry after {exc.retry_after}s")
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
attributes (`status_code`, `response_body`, `retry_after`, `ratelimit`, `method`,
`url`) and any notes, so an error raised in a `ProcessPoolExecutor` or
`multiprocessing` worker reaches the parent as the same class. As with any pickled
exception, `__cause__`, `__context__` and the traceback are not carried over.

A paginated iterator (`.list()`, `search()`) that raises keeps its place. Whether the
request for a page fails, the page's envelope has the wrong shape, or one of its items
fails validation (Pydantic's `ValidationError`), `page`, the totals and the URLs stay as
they were before that page, and the next `next()` or `anext()` requests the same page
again. Items already yielded are not repeated, and none are skipped.

A wrong shape raises `DiscogsError` naming the endpoint, the key and the JSON type
received, for example `GET /users/trent_reznor/submissions: "submissions" is null,
expected an object`. That covers a body that is not an object, a `pagination` or a
non-empty `pagination.urls` that is not an object, and an items key that is not an
array (or, for nested items, not an object on the way). An absent items key is an
empty page.

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
  is checked by the SDK itself, as described above; its items go to Pydantic like
  any other model.
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
