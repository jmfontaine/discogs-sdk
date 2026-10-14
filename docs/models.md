# Models

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
| `from` | `from_user` | `OrderMessage` |
| `list_id` | `id` | `List_` |
| `modified_ts` | `modified_at` | `List_` |
| `namevariations` | `name_variations` | `Artist` |
| `qty` | `quantity` | `Format` |
| `sublabels` | `sub_labels` | `Label` |
| `type_` | `type` | `Track` |
| `uri150` | `uri_150` | `Image` |

The Python name is the typed attribute. API names still resolve as attributes at runtime, but only dynamically: a type
checker treats them like any misspelled attribute, so read them through `getattr` where one is in play:

```python
from discogs_sdk import Discogs

client = Discogs()
release = client.releases.get(352665)  # The Downward Spiral
print(release.extra_artists)  # Python name, typed
print(getattr(release, "extraartists"))  # API name, runtime only — same value
```

An API name that is a Python keyword, such as `from`, is reachable only through `getattr(message, "from")`.

An API name resolves to the same normalized value as the Python name, so `getattr(export, "created_ts")` is a
`datetime` too. To read what Discogs sent, use [`raw`](#original-api-values).

Renaming a key and parsing a value are normalizations, which the SDK's
[design principles](../README.md#design-principles) allow only when nothing is lost, the result comes from the
response alone, and the change is documented on this page.

## Search result links

Every Discogs entity (release, master, artist, label, listing, order, user, list) carries an absolute `uri` linking to
its page, such as `https://www.discogs.com/release/352665`. `/database/search` results are the exception: Discogs
sends a site-relative path such as `/release/352665`. `SearchResult.uri` normalizes the value rather than renaming the
key: a path starting with `/` gets `https://www.discogs.com` prefixed and is otherwise kept as sent, percent-encoding
included. An absolute value and a missing one (`None`) are unchanged, and `raw["uri"]` keeps the relative path:

```python
from discogs_sdk import SearchResult

result = SearchResult.model_validate(
    {
        "id": 352665,
        "title": "Nine Inch Nails - The Downward Spiral",
        "uri": "/release/352665",
    }
)
print(result.uri)  # 'https://www.discogs.com/release/352665'
print(result.raw["uri"])  # '/release/352665'
```

## Shipping prices

A seller who set no shipping price on a listing sends `"shipping_price": {}` and `"original_shipping_price": {}`
instead of leaving the keys out or sending `null`. `Listing.shipping_price` and `Listing.original_shipping_price`
read an empty object as `None`, the same as an absent key, and `raw` keeps the `{}`. A price that is partly filled
in, such as a `currency` without a `value`, still fails validation:

```python
from discogs_sdk import Listing

listing = Listing.model_validate(
    {
        "id": 41578241,
        "price": {"currency": "USD", "value": 25.0},
        "shipping_price": {},
        "original_shipping_price": {},
    }
)
print(listing.shipping_price)  # None
print(listing.raw["shipping_price"])  # {}
```

## Timestamps

Discogs sends timestamps as strings in several shapes:

| Shape | Example | Where |
|---|---|---|
| ISO 8601 with an offset | `2005-01-03T23:17:26-08:00` | most fields |
| A space instead of `T` | `2011-08-30 14:21:45-07:00` | `User.registered` |
| No offset | `2026-10-11T07:07:34` | `Export` and `Upload` (`created_at`, `finished_at`) |

The SDK parses every one of them into a timezone-aware `datetime`, so you can compare and sort values from any
endpoint. This covers `Release` (`date_added`, `date_changed`), `CollectionItem.date_added`, `ListSummary`
(`date_added`, `date_changed`), `List_` (`created_at`, `modified_at`), `User.registered`, `Listing.posted`, `Order`
(`created`, `last_activity`), `OrderMessage.timestamp`, `Export` and `Upload` (`created_at`, `finished_at`).

- An offset that Discogs sends stays as sent.
- A value without an offset is read as `America/Los_Angeles` time and gets the fixed offset in force then (`-08:00` or
  `-07:00`), the same kind of `tzinfo` as a value that arrives with one. Discogs does not document its zone; this is an
  assumption. An export requested at 14:07:34 UTC reported `07:07:34`, and the offsets Discogs does send switch between
  `-08:00` and `-07:00` with daylight saving. In the hour repeated when daylight saving ends, the SDK picks the first
  occurrence.
- An empty string becomes `None`.
- A value the SDK cannot parse becomes `None`, and the SDK logs a warning on the `discogs_sdk` logger. The model still
  loads, and `raw` keeps the string.

`model_dump(mode="json")` writes ISO 8601 with an explicit offset, and `model_validate` reads it back unchanged.

## Original API values

Every model keeps the mapping it was validated from in `raw`. Use it to read a value as Discogs sent it, before
renaming or parsing:

```python
release = client.releases.get(352665)  # The Downward Spiral
print(release.date_added)  # datetime(2005, 1, 3, 23, 17, 26, tzinfo=...)
print(release.raw["date_added"])  # '2005-01-03T23:17:26-08:00'
print(release.extra_artists[0].raw)  # a nested model holds its own part of the payload
```

`raw` is the decoded response itself, not a copy; its type is a read-only `Mapping`, but code holding the same dict can
still change it, and later reads see the change. Holding a model keeps the whole payload in memory. `model_dump()` and
`==` ignore `raw`. A model you build with keyword arguments or with `model_validate(model.model_dump())` reports that
input instead of an API response.
