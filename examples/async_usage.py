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

        # ── Sub-resources still work without await ─────────────────
        # Sub-resource accessors never trigger HTTP, so no await needed.
        # Only the final .get() returns a lazy that needs awaiting.
        rating = await client.releases.get(352665).rating.get()
        print(f"Average: {rating.rating.average}")

        # ── Pagination with async for ─────────────────────────────
        async for result in client.search(query="Nine Inch Nails", type="artist"):
            print(f"  {result.title}")
            break

        # ── Artist releases ────────────────────────────────────────
        artist = await client.artists.get(3857)
        print(f"\nReleases by {artist.name}:")
        async for rel in artist.releases.list(sort="year"):
            print(f"  {rel.title} ({rel.year})")

        # ── Collection (requires OAuth) ────────────────────────────
        user = client.users.get("your_username")
        # Note: user itself is lazy, but sub-resource navigation
        # doesn't need await — only data access does.
        async for item in user.collection.folders.get(0).releases.list():
            info = item.basic_information
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
