"""Async usage — the same SDK with async/await.

Covers:
  - async with for client lifecycle
  - await for lazy resource resolution
  - async for for pagination
  - Side-by-side comparison with sync
"""

import asyncio

from discogs_sdk import AsyncDiscogs


async def main() -> None:
    # ── Client lifecycle ───────────────────────────────────────────
    # Use `async with` to ensure the HTTP client is closed.
    # Reads DISCOGS_TOKEN from the environment, or pass token="..." explicitly.
    async with AsyncDiscogs() as client:
        # ── Lazy resolution with await ─────────────────────────────
        # In async mode, LazyResource does NOT auto-resolve on attribute
        # access.  You must `await` it first to trigger the HTTP call.
        lazy = client.releases.get(352665)

        # BAD — raises AttributeError because the resource isn't resolved:
        # print(lazy.title)

        # GOOD — await resolves the resource, then access attributes:
        release = await lazy
        print(f"{release.title} ({release.year})")

        # Or in one expression:
        release = await client.releases.get(352665)
        print(release.title)

        # ── Proxy vs resolved model ────────────────────────────────
        # .get() returns a proxy. Awaiting it gives you the data model.
        # Sub-resource accessors live on the proxy, not on the model, and
        # never trigger HTTP — so keep the proxy when you need both.
        community = await client.releases.get(352665).rating.get()
        rating = community.rating
        if not isinstance(rating, int):
            print(f"Average: {rating.average}")

        # ── Pagination with async for ─────────────────────────────
        async for result in client.search(query="Nine Inch Nails", type="artist"):
            print(f"  {result.title}")
            break

        # ── Artist releases ────────────────────────────────────────
        artist_proxy = client.artists.get(3857)
        artist = await artist_proxy  # the Artist model
        print(f"\nReleases by {artist.name}:")
        # BAD — the resolved model has no sub-resources:
        # async for rel in artist.releases.list(sort="year"):
        async for rel in artist_proxy.releases.list(sort="year"):
            print(f"  {rel.title} ({rel.year})")

        # ── Collection (requires OAuth) ────────────────────────────
        user = client.users.get("your_username")
        # Note: user itself is lazy, but sub-resource navigation
        # doesn't need await — only data access does.
        async for item in user.collection.folders.get(0).releases.list():
            info = item.basic_information
            if info:
                print(f"  {info.title}")


asyncio.run(main())


# ━━ Sync vs Async comparison ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# ┌──────────────────────┬────────────────────────────────────────┐
# │ Sync                 │ Async                                  │
# ├──────────────────────┼────────────────────────────────────────┤
# │ from discogs_sdk     │ from discogs_sdk                       │
# │   import Discogs     │   import AsyncDiscogs                  │
# ├──────────────────────┼────────────────────────────────────────┤
# │ with Discogs() as c: │ async with AsyncDiscogs() as c:        │
# ├──────────────────────┼────────────────────────────────────────┤
# │ r = c.releases       │ r = await c.releases                   │
# │       .get(352665)   │             .get(352665)               │
# │ print(r.title)       │ print(r.title)                         │
# │ # auto-resolves on   │ # must await first                     │
# │ # attribute access   │                                        │
# ├──────────────────────┼────────────────────────────────────────┤
# │ for r in results:    │ async for r in results:                 │
# │     print(r.title)   │     print(r.title)                     │
# └──────────────────────┴────────────────────────────────────────┘
