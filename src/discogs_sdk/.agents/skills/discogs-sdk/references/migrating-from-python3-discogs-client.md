<!-- Generated from docs/migrating-from-python3-discogs-client.md by scripts/generate_skill_refs.py for v0.8.1; do not edit. -->

# Migrating from python3-discogs-client

[python3-discogs-client](https://github.com/joalla/discogs_client) (`import discogs_client`) and discogs-sdk
(`import discogs_sdk`) are separate packages with different APIs; nothing here is a drop-in alias. This page maps each
common idiom to its discogs-sdk counterpart and names where the behaviour differs. Where a row says "closest
equivalent", the semantics are not identical. The predecessor's side was checked against its source and docs at
[`58808df`](https://github.com/joalla/discogs_client/tree/58808df2d06aeabe00b1ee1e5fe547da137d2e45).

```bash
pip uninstall python3-discogs-client
pip install discogs-sdk
```

## Before and after

<!-- doc-test: skip (python3-discogs-client code, shown for comparison) -->
```python
import discogs_client

d = discogs_client.Client("MyApp/1.0", user_token="my_user_token")
release = d.release(352665)
print(release.title)
for artist in d.search("Nine Inch Nails", type="artist").page(1):
    print(artist.name)
me = d.identity()
for item in me.collection_folders[0].releases:
    print(item.release.title)
```

```python
from discogs_sdk import Discogs

client = Discogs()  # reads DISCOGS_TOKEN from the environment
release = client.releases.get(352665)
print(release.title)
for result in client.search(query="Nine Inch Nails", type="artist"):
    print(result.title)
identity = client.user.identity()
user = client.users.get(identity.username)
for item in user.collection.folders.get(0).releases.list():
    if item.basic_information:  # None when Discogs omits it
        print(item.basic_information.title)
```

## Translation table

| python3-discogs-client | discogs-sdk | Qualification |
|---|---|---|
| `discogs_client.Client("ua/1.0", user_token=t)` | `Discogs(token=t)`, or `Discogs()` with `DISCOGS_TOKEN` | Pass `user_agent="ua/1.0"` to keep the old custom header. |
| `d.release(id)`, `d.artist(id)`, `d.master(id)`, `d.label(id)` | `client.releases.get(id)`, `client.artists.get(id)`, `client.masters.get(id)`, `client.labels.get(id)` | All return lazy proxies. |
| `d.search(q, type="release").page(1)` | `for r in client.search(query=q, type="release")` | Closest equivalent. `.page(1)` fetches one page; SDK iteration continues through later pages until stopped. |
| `d.identity()` | `client.user.identity()` | Returns `Identity`, not the predecessor's full `User`; then `user = client.users.get(identity.username)`. |
| `me.collection_folders[0].releases` | `client.users.get(name).collection.folders.get(0).releases.list()` | Predecessor `[0]` is a list index; SDK `get(0)` is folder id 0 ("All"). |
| `me.wantlist.add(release, notes=…)` | `user.wantlist.create(release_id=…)`, then `user.wantlist.update(release_id, notes=…, rating=…)` | Create takes only the id: Discogs drops notes and rating on that endpoint. |
| `me.inventory.add_listing(release=…, condition=Condition.MINT, price=…, status=Status.FOR_SALE)` | `client.marketplace.listings.create(release_id=…, condition="Mint (M)", price=…)` | Upstream requires `status`; the SDK defaults to `"For Sale"`. Conditions are plain strings, checked by a type checker. |
| `d.backoff_enabled = False` | `Discogs(max_retries=0)` | Closest equivalent. Also disables transport and 5xx retries, not just 429 backoff. |
| `client.set_timeout(connect=…, read=…)` | `Discogs(timeout=…)` | Closest equivalent. One float; separate connect/read values need an injected `httpx2` client. The predecessor has no timeout until configured; the SDK defaults to 30 s. |
| `.data[...]`, `.fetch("key")` | Typed attributes; original payload in `model.raw` | After an async `await`, keep the proxy for sub-resource chaining. |
| `client._fetcher.rate_limit*` | `client.ratelimit` | `None` until a response carries all three rate-limit headers; a later response without them keeps the last value. Guard it. |

The writes from the table, in discogs-sdk:

```python
user.wantlist.create(release_id=352665)  # the release id and nothing else
user.wantlist.update(352665, notes="Original pressing", rating=4)

created = client.marketplace.listings.create(
    release_id=352665,
    condition="Mint (M)",  # one of the Condition literals
    price=25.00,
)  # status defaults to "For Sale"
print(created.listing_id)
```

## Behaviour differences

**Lazy loading.** Both libraries defer the request, but `client.releases.get(352665)` sends nothing at all: the first
data attribute access sends the GET, and that is where `NotFoundError` is raised, so put the `try` around the
attribute access. With `AsyncDiscogs`, `await` the proxy instead. See
[Behaviors to know](getting-started.md#lazy-loading).

**Iteration instead of `.page(n)`.** A page has no `.page(n)`, `.pages` or `.count`, and no `len()` or indexing.
Iterate it, and `break` once you have enough; each page costs a request against the rate limit. `per_page` sets the
page size, and `total_items`/`total_pages` are filled in once the first page arrives. See
[Pagination](pagination.md).

**Typed models instead of `.data`.** Every field is a typed attribute with a Python name: `catalog_number` rather than
`catno`, `extra_artists` rather than `extraartists` (the full list is in [Models](https://github.com/jmfontaine/discogs-sdk/blob/v0.8.1/docs/models.md#field-naming)).
Timestamps are timezone-aware `datetime` objects. What Discogs sent is still in `model.raw`. In the async client,
`await client.artists.get(3857)` returns the `Artist` model, which has no `releases`: keep the proxy to chain.

**Retries.** The predecessor backs off on HTTP 429 until `backoff_enabled` is turned off. discogs-sdk retries reads on
429, 500, 502, 503 and 504 and on transient transport failures, up to `max_retries` times (3 by default), honouring
`Retry-After` up to 60 seconds. A `POST`, `PUT` or `DELETE` that may have reached the server is never sent again. See
[Errors and retries](errors-and-retries.md#rate-limits-and-retries).

**Default timeout.** The predecessor waits indefinitely until `set_timeout()` is called. discogs-sdk times out after 30
seconds by default. For separate connect and read limits, inject your own `httpx2` client; the SDK never closes it:

```python
import httpx2

from discogs_sdk import Discogs

with httpx2.Client(timeout=httpx2.Timeout(10.0, connect=5.0)) as http:
    timed_client = Discogs(http_client=http)
    print(timed_client.releases.get(352665).title)
```

**Rate-limit headers.** The predecessor overwrites its counters on every response. `client.ratelimit` is `None` until
a network response carries all three `X-Discogs-Ratelimit*` headers, and after that a response without them leaves
the last value in place, so a value is not proof the latest response had the headers. Guard against `None`:

```python
if client.ratelimit is not None and client.ratelimit.remaining < 5:
    print("Close to the limit; slow down")
```

## User objects

The predecessor's `identity()` returns a `User` with collection and wantlist accessors. discogs-sdk's `Identity` holds
only `id`, `username`, `consumer_name` and `resource_url`; the collection, wantlist, inventory and lists live on the
user proxy, so build one from the username (see [The authenticated user](https://github.com/jmfontaine/discogs-sdk/blob/v0.8.1/docs/authentication.md#the-authenticated-user)):

```python
identity = client.user.identity()
me = client.users.get(identity.username)
print(me.collection.value.get().median)
```

## Exceptions

The predecessor's root is `DiscogsAPIError`, with `HTTPError`, `AuthorizationError`, `ConfigurationError`,
`TooManyAttemptsError` and `MalformedResponseError` beneath it. discogs-sdk's root is `DiscogsError`, and its own
`DiscogsAPIError` covers only HTTP-status errors, with a subclass per status (`AuthenticationError`, `ForbiddenError`,
`NotFoundError`, `ValidationError`, `RateLimitError`). Porting `except DiscogsAPIError` by name therefore misses
`DiscogsConnectionError`, `CacheMissError` and `CacheError`; catch `DiscogsError` for everything the SDK raises.

The predecessor wraps a body that is not JSON (or not UTF-8) in `MalformedResponseError`. discogs-sdk lets
`json.JSONDecodeError` and `UnicodeDecodeError` through on a 2xx, and `pydantic.ValidationError` when the JSON does not
fit the model; an error status is mapped to its `DiscogsAPIError` before the body is parsed. None of these is a
connection problem, so do not map `MalformedResponseError` to `DiscogsConnectionError`. See
[Exceptions outside `DiscogsError`](errors-and-retries.md#exceptions-outside-discogserror).

```python
import json

import pydantic

from discogs_sdk import DiscogsError, NotFoundError, RateLimitError

try:
    print(client.releases.get(352665).title)
except NotFoundError:
    print("No such release")
except RateLimitError as exc:
    print(f"Rate limited; Retry-After: {exc.retry_after}")
except DiscogsError as exc:  # every other SDK error, connection failures included
    print(f"Discogs request failed: {exc}")
except (json.JSONDecodeError, UnicodeDecodeError, pydantic.ValidationError) as exc:
    print(f"Discogs answered with a body the SDK could not parse: {exc}")
```
