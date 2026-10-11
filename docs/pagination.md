# Pagination

## What a page costs

Paginated methods (`search()` and the `.list()` methods returning `SyncPage`/`AsyncPage`) fetch pages on demand. Each
page starts a logical GET: a cache hit sends no network request, and retries can send several. Each network attempt
consumes the applicable budget (60/min authenticated, 25/min anonymous). These methods accept `per_page`, have no
`len()` or slicing, and populate `total_items`/`total_pages` from the first fetched response when it supplies them.
`collection.folders.list()` and `collection.fields.list()` each make one logical GET and return a plain list.

Retries follow the client's `max_retries`: a page that keeps failing with a retryable error sends up to
`max_retries + 1` attempts, four by default (see [Errors and retries](errors-and-retries.md#rate-limits-and-retries)).
Calling `.list()` or `search()` sends nothing; the first page is requested when iteration starts.

## Stopping early

Iterate only as far as you need and `break`: no later page is requested. A larger `per_page` (Discogs allows up to
100) means fewer requests for the same items. Never pass a large result set to `list()` or a comprehension, which
pages through all of it.

```python
from discogs_sdk import Discogs

client = Discogs()
results = client.search(query="Nine Inch Nails", type="release", per_page=25)
print(results.total_items)  # None: no page fetched yet

for count, result in enumerate(results, start=1):
    print(result.title)
    if count == 10:
        break  # no further page is requested

print(results.page, results.per_page, results.total_items, results.total_pages)
print(results.next_url)  # the next page's URL, or None on the last page
```

With `AsyncDiscogs`, iterate with `async for`; the attributes are the same. The two lists that are not paginated come
back whole from one request:

```python
user = client.users.get(client.user.identity().username)
folders = user.collection.folders.list()  # one GET, a plain list
print(len(folders), folders[0].name)
```

## Page attributes

Every attribute is `None` until the first page has been fetched, and is updated with each page after that.

| Attribute | Meaning |
|---|---|
| `page` | Number of the page fetched last |
| `per_page` | Items per page, as Discogs reports it |
| `total_items` | Items across all pages, when the response supplies it |
| `total_pages` | Number of pages, when the response supplies it |
| `first_url`, `prev_url`, `last_url` | Links from the response's `pagination.urls`; `None` when it omits them |
| `next_url` | URL of the next page; `None` on the last page |

## When a page fails

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

## One consumer, one pass

A page returned by `.list()` or `search()` is a single-pass iterator for one consumer. Several threads or tasks
iterating the same page race on its position and can fetch a page twice and yield its items twice, and a page that
is exhausted yields nothing on a second pass. Call `.list()` or `search()` again for each consumer and each pass.
