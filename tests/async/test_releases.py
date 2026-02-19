"""Tests for async Releases resource."""

from __future__ import annotations

import httpx
import pytest

from discogs_sdk.models.release import (
    CommunityRating,
    MarketplaceReleaseStats,
    PriceSuggestions,
    Release,
    ReleaseStats,
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

    async def test_get_resolves_to_release(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(return_value=httpx.Response(200, json=make_release()))
        result = await client.releases.get(400027)
        assert isinstance(result, Release)
        assert result.id == 400027
        assert result.title == "The Downward Spiral"


class TestReleaseSubResources:
    def test_rating_accessible_without_http(self, client, respx_mock):
        lazy = client.releases.get(400027)
        _ = lazy.rating
        assert respx_mock.calls.call_count == 0

    def test_stats_accessible_without_http(self, client, respx_mock):
        lazy = client.releases.get(400027)
        _ = lazy.stats
        assert respx_mock.calls.call_count == 0

    def test_price_suggestions_accessible_without_http(self, client, respx_mock):
        lazy = client.releases.get(400027)
        _ = lazy.price_suggestions
        assert respx_mock.calls.call_count == 0

    def test_marketplace_stats_accessible_without_http(self, client, respx_mock):
        lazy = client.releases.get(400027)
        _ = lazy.marketplace_stats
        assert respx_mock.calls.call_count == 0


class TestReleaseRating:
    async def test_community_rating(self, client, respx_mock):
        respx_mock.get("/releases/400027/rating").mock(return_value=httpx.Response(200, json=make_community_rating()))
        lazy = client.releases.get(400027)
        result = await lazy.rating.get()
        assert isinstance(result, CommunityRating)
        assert result.release_id == 400027

    async def test_user_rating(self, client, respx_mock):
        respx_mock.get("/releases/400027/rating/trent_reznor").mock(
            return_value=httpx.Response(200, json=make_user_release_rating())
        )
        lazy = client.releases.get(400027)
        result = await lazy.rating.get("trent_reznor")
        assert isinstance(result, UserReleaseRating)
        assert result.username == "trent_reznor"
        assert result.rating == 5

    async def test_update_rating(self, client, respx_mock):
        respx_mock.put("/releases/400027/rating/trent_reznor").mock(
            return_value=httpx.Response(200, json=make_user_release_rating(rating=4))
        )
        lazy = client.releases.get(400027)
        result = await lazy.rating.update("trent_reznor", 4)
        assert isinstance(result, UserReleaseRating)
        assert result.rating == 4

    async def test_delete_rating(self, client, respx_mock):
        respx_mock.delete("/releases/400027/rating/trent_reznor").mock(return_value=httpx.Response(204))
        lazy = client.releases.get(400027)
        await lazy.rating.delete("trent_reznor")  # should not raise

    async def test_delete_rating_error_empty_body(self, client, respx_mock):
        respx_mock.delete("/releases/400027/rating/trent_reznor").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        lazy = client.releases.get(400027)
        from discogs_sdk._exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await lazy.rating.delete("trent_reznor")


class TestReleaseStats:
    async def test_stats_get(self, client, respx_mock):
        respx_mock.get("/releases/400027/stats").mock(return_value=httpx.Response(200, json=make_release_stats()))
        lazy = client.releases.get(400027)
        result = await lazy.stats.get()
        assert isinstance(result, ReleaseStats)
        assert result.num_have == 1000


class TestReleasePriceSuggestions:
    async def test_price_suggestions_get(self, client, respx_mock):
        respx_mock.get("/marketplace/price_suggestions/400027").mock(return_value=httpx.Response(200, json={}))
        lazy = client.releases.get(400027)
        result = await lazy.price_suggestions.get()
        assert isinstance(result, PriceSuggestions)

    async def test_price_suggestions_conditions(self, client, respx_mock):
        body = {
            "Mint (M)": {"currency": "USD", "value": 25.00},
            "Very Good Plus (VG+)": {"currency": "USD", "value": 15.00},
        }
        respx_mock.get("/marketplace/price_suggestions/400027").mock(return_value=httpx.Response(200, json=body))
        result = await client.releases.get(400027).price_suggestions.get()
        conditions = result.conditions
        assert len(conditions) == 2
        assert conditions["Mint (M)"].value == 25.00
        assert conditions["Mint (M)"].currency == "USD"

    async def test_price_suggestions_getitem(self, client, respx_mock):
        body = {"Mint (M)": {"currency": "USD", "value": 25.00}}
        respx_mock.get("/marketplace/price_suggestions/400027").mock(return_value=httpx.Response(200, json=body))
        result = await client.releases.get(400027).price_suggestions.get()
        assert result["Mint (M)"].value == 25.00
        with pytest.raises(KeyError):
            result["No Such Condition"]


class TestReleaseMarketplaceStats:
    async def test_marketplace_stats_get(self, client, respx_mock):
        respx_mock.get("/marketplace/stats/400027").mock(return_value=httpx.Response(200, json={"num_for_sale": 10}))
        lazy = client.releases.get(400027)
        result = await lazy.marketplace_stats.get()
        assert isinstance(result, MarketplaceReleaseStats)
        assert result.num_for_sale == 10


class TestReleaseModel:
    async def test_required_fields(self, client, respx_mock):
        respx_mock.get("/releases/1").mock(return_value=httpx.Response(200, json={"id": 1, "title": "T"}))
        result = await client.releases.get(1)
        assert result.id == 1
        assert result.year is None

    async def test_extra_allow(self, client, respx_mock):
        respx_mock.get("/releases/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "title": "T", "unknown_field": "val"})
        )
        result = await client.releases.get(1)
        assert result.model_extra["unknown_field"] == "val"
