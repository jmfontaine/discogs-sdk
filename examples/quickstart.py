"""Quickstart — your first requests with the Discogs SDK.

Covers:
  - Installing the SDK
  - Token authentication
  - Context manager usage
  - Fetching a release (lazy resolution)
  - Iterating search results (auto-pagination)
"""

# Install:  pip install discogs-sdk  (or: uv add discogs-sdk)

from discogs_sdk import Discogs

# ── Authenticate with a personal access token ──────────────────────
# Generate one at https://www.discogs.com/settings/developers
#
# Option 1 (recommended): set the DISCOGS_TOKEN env var and let the
# SDK pick it up automatically — avoids hardcoding secrets in code.
client = Discogs()

# Option 2: pass the token explicitly.
client = Discogs(token="YOUR_TOKEN_HERE")

# Use a context manager so the HTTP client is closed automatically:
with Discogs() as client:
    # ── Fetch a release ────────────────────────────────────────────
    # .get() returns a LazyResource — no HTTP request yet.
    release = client.releases.get(352665)

    # The first attribute access triggers the GET request and resolves
    # the full Release model transparently.
    print(release.title)  # "The Downward Spiral"
    print(release.year)  # 1994

    # ── Search the database ────────────────────────────────────────
    # search() returns a paginated iterator.  The SDK fetches pages
    # automatically as you iterate.
    results = client.search(query="Nine Inch Nails", type="artist")

    for result in results:
        print(f"{result.title} ({result.type})")
        break  # just show the first hit

    # ── Navigate sub-resources ─────────────────────────────────────
    # Sub-resource accessors (like .rating) never trigger HTTP.
    # Only the final .get() / .list() creates a lazy or paginated object.
    rating = client.releases.get(352665).rating.get()
    print(rating.rating)  # CommunityRating with average and count

    # ── Browse an artist's releases ────────────────────────────────
    artist = client.artists.get(3857)  # Nine Inch Nails
    print(artist.name)

    for rel in artist.releases.list(sort="year", sort_order="desc"):
        print(f"  {rel.title} ({rel.year})")
