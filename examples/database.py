"""Database — browsing releases, artists, masters, labels, and search.

Covers:
  - Release: get, community rating, user rating CRUD, stats,
    price suggestions, marketplace stats
  - Artist: get, list releases with sorting
  - Master: get, list versions with filters
  - Label: get, list releases
  - Search: query with filters, pagination
"""

from discogs_sdk import Discogs

# Reads DISCOGS_TOKEN from the environment, or pass token="..." explicitly.
client = Discogs()

# ━━ Releases ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Fetch a release.  .get() returns a LazyResource — the HTTP call
# happens when you first access an attribute.
release = client.releases.get(352665)  # The Downward Spiral
print(f"{release.title} ({release.year})")
print(f"Artists: {[a.name for a in release.artists]}")

# Community rating (no auth required).
community = client.releases.get(352665).rating.get()
print(f"Average: {community.rating.average}, Count: {community.rating.count}")

# Your personal rating (requires auth).
my_rating = client.releases.get(352665).rating.get(username="your_username")
print(f"My rating: {my_rating.rating}")

# Set your rating (1-5).
client.releases.get(352665).rating.update(username="your_username", rating=5)

# Remove your rating.
client.releases.get(352665).rating.delete(username="your_username")

# Release stats — num_have / num_want (requires auth for full data).
stats = client.releases.get(352665).stats.get()
print(f"Have: {stats.num_have}, Want: {stats.num_want}")

# Price suggestions (requires auth).
prices = client.releases.get(352665).price_suggestions.get()
print(prices["Mint (M)"].value)  # bracket access by condition name
for condition, price in prices.conditions.items():
    print(f"  {condition}: {price.currency} {price.value}")

# Marketplace stats for a release.
market = client.releases.get(352665).marketplace_stats.get()
print(f"Lowest: {market.lowest_price}, For sale: {market.num_for_sale}")


# ━━ Artists ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

artist = client.artists.get(3857)  # Nine Inch Nails
print(f"{artist.name}: {artist.profile[:80]}...")

# List an artist's releases with sorting.
# Sorts: "year", "title", "format".  Orders: "asc", "desc".
for rel in artist.releases.list(sort="year", sort_order="desc"):
    print(f"  {rel.title} ({rel.year}) [{rel.type}]")


# ━━ Masters ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

master = client.masters.get(3719)  # The Downward Spiral (master)
print(f"{master.title} ({master.year})")

# List all versions of a master, with optional filters.
for version in master.versions.list(
    format="Vinyl",
    country="US",
    sort="released",
    sort_order="asc",
):
    print(f"  {version.title} [{version.format}] - {version.country}")


# ━━ Labels ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

label = client.labels.get(647)  # Nothing Records
print(f"{label.name}")

# List releases on a label (paginated).
for rel in label.releases.list():
    print(f"  {rel.title} by {rel.artist}")


# ━━ Search ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Basic text search.
for result in client.search(query="Pretty Hate Machine"):
    print(f"  [{result.type}] {result.title}")

# Filtered search — combine any Discogs search parameters.
for result in client.search(
    query="Nine Inch Nails",
    type="release",
    year="1994",
    format="CD",
    country="US",
):
    print(f"  {result.title} ({result.year})")

# Search returns a paginated iterator.  The SDK fetches the next page
# automatically when you exhaust the current one.
