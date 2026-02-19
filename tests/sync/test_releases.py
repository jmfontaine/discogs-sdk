"""Tests for sync Releases resource."""

from __future__ import annotations

import httpx
import pytest

from discogs_sdk._exceptions import NotFoundError
from discogs_sdk.models.release import (
    UserReleaseRating,
)

from tests.conftest import (
    make_community_rating,
    make_release,
    make_release_stats,
    make_user_release_rating,
)


class TestReleasesGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.releases.get(400027)
        assert respx_mock.calls.call_count == 0

    def test_get_resolves_to_release(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(return_value=httpx.Response(200, json=make_release()))
        lazy = client.releases.get(400027)
        assert lazy.title == "The Downward Spiral"
        assert lazy.id == 400027


class TestReleaseSubResources:
    def test_all_sub_resources_no_http(self, client, respx_mock):
        lazy = client.releases.get(400027)
        _ = lazy.rating
        _ = lazy.stats
        _ = lazy.price_suggestions
        _ = lazy.marketplace_stats
        assert respx_mock.calls.call_count == 0


class TestReleaseRating:
    def test_community_rating(self, client, respx_mock):
        respx_mock.get("/releases/400027/rating").mock(return_value=httpx.Response(200, json=make_community_rating()))
        lazy = client.releases.get(400027)
        result = lazy.rating.get()
        assert result.release_id == 400027

    def test_user_rating(self, client, respx_mock):
        respx_mock.get("/releases/400027/rating/trent_reznor").mock(
            return_value=httpx.Response(200, json=make_user_release_rating())
        )
        lazy = client.releases.get(400027)
        result = lazy.rating.get("trent_reznor")
        assert result.username == "trent_reznor"

    def test_update_rating(self, client, respx_mock):
        respx_mock.put("/releases/400027/rating/trent_reznor").mock(
            return_value=httpx.Response(200, json=make_user_release_rating(rating=4))
        )
        lazy = client.releases.get(400027)
        result = lazy.rating.update("trent_reznor", 4)
        assert isinstance(result, UserReleaseRating)

    def test_delete_rating(self, client, respx_mock):
        respx_mock.delete("/releases/400027/rating/trent_reznor").mock(return_value=httpx.Response(204))
        lazy = client.releases.get(400027)
        lazy.rating.delete("trent_reznor")

    def test_delete_rating_error(self, client, respx_mock):
        respx_mock.delete("/releases/400027/rating/trent_reznor").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        lazy = client.releases.get(400027)
        with pytest.raises(NotFoundError):
            lazy.rating.delete("trent_reznor")


class TestReleaseStats:
    def test_stats_get(self, client, respx_mock):
        respx_mock.get("/releases/400027/stats").mock(return_value=httpx.Response(200, json=make_release_stats()))
        lazy = client.releases.get(400027)
        result = lazy.stats.get()
        assert result.num_have == 1000


class TestReleasePriceSuggestions:
    def test_price_suggestions_get(self, client, respx_mock):
        respx_mock.get("/marketplace/price_suggestions/400027").mock(
            return_value=httpx.Response(200, json={"Mint (M)": {"value": 50.0, "currency": "USD"}})
        )
        lazy = client.releases.get(400027)
        result = lazy.price_suggestions.get()
        assert result["Mint (M)"].value == 50.0

    def test_price_suggestions_conditions(self, client, respx_mock):
        body = {
            "Mint (M)": {"currency": "USD", "value": 25.00},
            "Very Good Plus (VG+)": {"currency": "USD", "value": 15.00},
        }
        respx_mock.get("/marketplace/price_suggestions/400027").mock(return_value=httpx.Response(200, json=body))
        result = client.releases.get(400027).price_suggestions.get()
        conditions = result.conditions
        assert len(conditions) == 2
        assert conditions["Mint (M)"].value == 25.00
        assert conditions["Mint (M)"].currency == "USD"

    def test_price_suggestions_getitem_missing(self, client, respx_mock):
        respx_mock.get("/marketplace/price_suggestions/400027").mock(return_value=httpx.Response(200, json={}))
        result = client.releases.get(400027).price_suggestions.get()
        with pytest.raises(KeyError):
            result["No Such Condition"]


class TestReleaseMarketplaceStats:
    def test_marketplace_stats_get(self, client, respx_mock):
        respx_mock.get("/marketplace/stats/400027").mock(return_value=httpx.Response(200, json={"num_for_sale": 10}))
        lazy = client.releases.get(400027)
        result = lazy.marketplace_stats.get()
        assert result.num_for_sale == 10


class TestReleaseModel:
    def test_required_fields(self, client, respx_mock):
        respx_mock.get("/releases/1").mock(return_value=httpx.Response(200, json={"id": 1, "title": "T"}))
        lazy = client.releases.get(1)
        assert lazy.year is None

    def test_extra_allow(self, client, respx_mock):
        respx_mock.get("/releases/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "title": "T", "unknown_field": "val"})
        )
        lazy = client.releases.get(1)
        assert lazy.model_extra["unknown_field"] == "val"
