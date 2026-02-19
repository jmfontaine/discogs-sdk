"""Shared payload factory helpers for building Discogs API response bodies."""

from __future__ import annotations

from typing import Any

import pytest

BASE_URL = "https://api.discogs.com"

_DISCOGS_ENV_VARS = (
    "DISCOGS_ACCESS_TOKEN",
    "DISCOGS_ACCESS_TOKEN_SECRET",
    "DISCOGS_CONSUMER_KEY",
    "DISCOGS_CONSUMER_SECRET",
    "DISCOGS_TOKEN",
)


@pytest.fixture(autouse=True)
def _clean_discogs_env(monkeypatch):
    """Prevent real credentials in the environment from leaking into unit tests."""
    for var in _DISCOGS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def make_artist(id: int = 40, name: str = "Nine Inch Nails") -> dict[str, Any]:
    return {"id": id, "name": name}


def make_artist_release(
    id: int = 1,
    title: str = "Pretty Hate Machine",
    type: str = "master",
) -> dict[str, Any]:
    return {"id": id, "title": title, "type": type}


def make_collection_field(id: int = 1, name: str = "Media Condition", type: str = "dropdown") -> dict[str, Any]:
    return {"id": id, "name": name, "type": type}


def make_collection_folder(id: int = 0, name: str = "All", count: int = 10) -> dict[str, Any]:
    return {"id": id, "name": name, "count": count}


def make_collection_item(
    id: int = 400027,
    instance_id: int = 1,
    folder_id: int = 0,
) -> dict[str, Any]:
    return {"id": id, "instance_id": instance_id, "folder_id": folder_id}


def make_collection_value() -> dict[str, Any]:
    return {"median": "$10.00", "minimum": "$1.00", "maximum": "$100.00"}


def make_community_rating(release_id: int = 400027) -> dict[str, Any]:
    return {"release_id": release_id, "rating": {"average": 4.5, "count": 100}}


def make_export(id: int = 1, status: str = "pending") -> dict[str, Any]:
    return {"id": id, "status": status}


def make_fee(value: float = 0.99, currency: str = "USD") -> dict[str, Any]:
    return {"value": value, "currency": currency}


def make_identity(id: int = 1, username: str = "trent_reznor") -> dict[str, Any]:
    return {"id": id, "username": username, "consumer_name": "NINApp"}


def make_paginated_response(
    items_key: str,
    items: list[dict[str, Any]],
    *,
    page: int = 1,
    pages: int = 1,
    next_url: str | None = None,
) -> dict[str, Any]:
    urls: dict[str, str] = {}
    if next_url:
        urls["next"] = next_url
    return {
        "pagination": {
            "page": page,
            "pages": pages,
            "per_page": 50,
            "items": len(items),
            "urls": urls,
        },
        items_key: items,
    }


def make_label(id: int = 26011, name: str = "Nothing Records") -> dict[str, Any]:
    return {"id": id, "name": name}


def make_label_release(id: int = 1, title: str = "Head Like a Hole") -> dict[str, Any]:
    return {"id": id, "title": title}


def make_list(id: int = 1, name: str = "Industrial Essentials") -> dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "items": [{"id": 1, "display_title": "The Downward Spiral", "type": "release"}],
    }


def make_list_summary(id: int = 1, name: str = "Industrial Essentials") -> dict[str, Any]:
    return {"id": id, "name": name}


def make_listing(
    id: int = 123,
    status: str = "For Sale",
) -> dict[str, Any]:
    return {"id": id, "status": status, "price": {"value": 9.99, "currency": "USD"}}


def make_master(id: int = 5765, title: str = "The Downward Spiral") -> dict[str, Any]:
    return {"id": id, "title": title}


def make_master_version(id: int = 1, title: str = "The Downward Spiral (Definitive Edition)") -> dict[str, Any]:
    return {"id": id, "title": title}


def make_order(id: str = "1-1", status: str = "New Order") -> dict[str, Any]:
    return {"id": id, "status": status}


def make_order_message(message: str = "Hello") -> dict[str, Any]:
    return {"message": message, "timestamp": "2024-01-01T00:00:00-00:00"}


def make_release(
    id: int = 400027,
    title: str = "The Downward Spiral",
    year: int | None = 1994,
) -> dict[str, Any]:
    d: dict[str, Any] = {"id": id, "title": title}
    if year is not None:
        d["year"] = year
    return d


def make_release_stats() -> dict[str, Any]:
    return {"num_have": 1000, "num_want": 500}


def make_search_result(
    id: int = 400027,
    title: str = "Nine Inch Nails - The Downward Spiral",
    type: str = "release",
) -> dict[str, Any]:
    return {"id": id, "title": title, "type": type}


def make_upload(id: int = 1, status: str = "pending") -> dict[str, Any]:
    return {"id": id, "status": status, "filename": "inventory.csv"}


def make_user(id: int = 1, username: str = "trent_reznor") -> dict[str, Any]:
    return {"id": id, "username": username}


def make_user_release_rating(
    release_id: int = 400027,
    username: str = "trent_reznor",
    rating: int = 5,
) -> dict[str, Any]:
    return {"release_id": release_id, "username": username, "rating": rating}


def make_want(
    id: int = 400027,
    notes: str | None = None,
    rating: int | None = None,
) -> dict[str, Any]:
    d: dict[str, Any] = {"id": id, "basic_information": {"id": id, "title": "The Downward Spiral"}}
    if notes is not None:
        d["notes"] = notes
    if rating is not None:
        d["rating"] = rating
    return d
