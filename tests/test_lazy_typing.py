"""Consumers must get concrete types from the lazy proxies and resource methods.

These run the project's type checker over short consumer snippets built from
public imports only. They assert whether the checker accepts the snippet, never
the wording of a diagnostic.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

VALID = """
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from discogs_sdk import AsyncDiscogs, CommunityRating, Discogs, RatingInfo
from discogs_sdk.models.artist import Artist
from discogs_sdk.models.release import Release


def sync_usage(client: Discogs) -> None:
    title: str = client.releases.get(352665).title
    year: int | None = client.releases.get(352665).year
    print(title, year)
    added: datetime | None = client.releases.get(352665).date_added
    payload: Mapping[str, Any] = client.releases.get(352665).raw
    print(added, payload)
    for release in client.artists.get(3857).releases.list(sort="year"):
        release_title: str = release.title
        print(release_title)
    client.releases.get(352665).rating.get(username="trent_reznor")
    average: float = client.releases.get(352665).rating.get().rating.average
    user_rating: int = client.releases.get(352665).rating.get("trent_reznor").rating
    print(average, user_rating)
    client.releases.get(352665).rating.get(None)
    client.users.get("trent_reznor").collection.folders.get(1).releases.get(352665).instances.get(20).fields


def maybe_user_rating(client: Discogs, username: str | None) -> None:
    client.releases.get(352665).rating.get(username)


def rating_info_usage(community_rating: CommunityRating) -> None:
    info: RatingInfo = community_rating.rating
    print(info.average, info.count)


async def async_rating_usage(client: AsyncDiscogs) -> None:
    community = await client.releases.get(352665).rating.get()
    community_average: float = community.rating.average
    mine = await client.releases.get(352665).rating.get("trent_reznor")
    mine_rating: int = mine.rating
    print(community_average, mine_rating)


async def async_usage(client: AsyncDiscogs) -> None:
    release: Release = await client.releases.get(352665)
    artist: Artist = await client.artists.get(3857)
    print(release.title, artist.name)
    proxy = client.artists.get(3857)
    async for item in proxy.releases.list():
        item_title: str = item.title
        print(item_title)


def mutation_usage(client: Discogs) -> None:
    instances = client.users.get("trent_reznor").collection.folders.get(1).releases.get(352665).instances
    instances.update(20, folder_id=2, rating=5)
    client.users.get("trent_reznor").wantlist.update(352665, notes="Original pressing", rating=4)
    client.marketplace.orders.update("12345-1", tracking={"number": "1Z999", "carrier": "UPS"})
    created = client.marketplace.listings.create(
        release_id=352665,
        condition="Very Good Plus (VG+)",
        price=25.00,
        sleeve_condition="Generic",
        weight="auto",
        format_quantity="auto",
    )
    client.marketplace.listings.update(created.listing_id, price=22.50, allow_offers=True)


async def async_mutation_usage(client: AsyncDiscogs) -> None:
    await client.marketplace.orders.update("12345-1", status="Shipped")
"""

INVALID_SNIPPETS = {
    "misspelled_sync_field": """
from discogs_sdk import Discogs


def usage(client: Discogs) -> None:
    print(client.releases.get(352665).titel)
""",
    "misspelled_subresource": """
from discogs_sdk import Discogs


def usage(client: Discogs) -> None:
    client.releases.get(352665).ratings
""",
    "wrong_argument_type": """
from discogs_sdk import Discogs


def usage(client: Discogs) -> None:
    client.releases.get("352665")
""",
    "async_field_without_await": """
from discogs_sdk import AsyncDiscogs


def usage(client: AsyncDiscogs) -> None:
    print(client.releases.get(352665).title)
""",
    "average_on_user_rating": """
from discogs_sdk import Discogs


def usage(client: Discogs) -> None:
    print(client.releases.get(352665).rating.get("trent_reznor").rating.average)
""",
    "misspelled_awaited_model_field": """
from discogs_sdk import AsyncDiscogs


async def usage(client: AsyncDiscogs) -> None:
    release = await client.releases.get(352665)
    print(release.titel)
""",
    "misspelled_paginated_item_field": """
from discogs_sdk import Discogs


def usage(client: Discogs) -> None:
    for release in client.artists.get(3857).releases.list():
        print(release.titel)
""",
    "misspelled_embedded_list_item_field": """
from discogs_sdk import AsyncDiscogs


async def usage(client: AsyncDiscogs) -> None:
    release = await client.releases.get(352665)
    for track in release.tracklist or []:
        print(track.titel)
""",
    "misspelled_sync_mutation_keyword": """
from discogs_sdk import Discogs


def usage(client: Discogs) -> None:
    instances = client.users.get("trent_reznor").collection.folders.get(1).releases.get(352665).instances
    instances.update(20, ratings=5)
""",
    "misspelled_async_mutation_keyword": """
from discogs_sdk import AsyncDiscogs


async def usage(client: AsyncDiscogs) -> None:
    await client.marketplace.orders.update("12345-1", statuz="Shipped")
""",
}


def _type_check(tmp_path: Path, source: str) -> subprocess.CompletedProcess[str]:
    snippet = tmp_path / "consumer.py"
    snippet.write_text(source)
    return subprocess.run(
        # Check against the interpreter running the tests: without it, ty picks up
        # any activated VIRTUAL_ENV, which may lack pydantic (CI's wheel jobs).
        [sys.executable, "-m", "ty", "check", "--python", sys.executable, str(snippet)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )


def test_supported_usage_type_checks(tmp_path):
    result = _type_check(tmp_path, VALID)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", sorted(INVALID_SNIPPETS))
def test_unsupported_usage_is_rejected(tmp_path, name):
    result = _type_check(tmp_path, INVALID_SNIPPETS[name])
    assert result.returncode != 0, result.stdout + result.stderr
