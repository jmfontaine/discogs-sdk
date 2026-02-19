"""Tests for AsyncLazyResource."""

from __future__ import annotations

import httpx
import pytest

from discogs_sdk._exceptions import NotFoundError
from discogs_sdk.models.release import Release

from tests.conftest import make_release


class TestCreation:
    def test_no_http_on_creation(self, client, respx_mock):
        _lazy = client.releases.get(400027)
        assert respx_mock.calls.call_count == 0

    def test_repr_before_resolve(self, client):
        lazy = client.releases.get(400027)
        r = repr(lazy)
        assert "AsyncLazyResource" in r
        assert "Release" in r
        assert "/releases/400027" in r


class TestResolve:
    async def test_await_triggers_http(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(return_value=httpx.Response(200, json=make_release()))
        lazy = client.releases.get(400027)
        result = await lazy
        assert isinstance(result, Release)
        assert result.id == 400027
        assert result.title == "The Downward Spiral"
        assert respx_mock.calls.call_count == 1

    async def test_second_await_cached(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(return_value=httpx.Response(200, json=make_release()))
        lazy = client.releases.get(400027)
        await lazy
        await lazy
        assert respx_mock.calls.call_count == 1

    async def test_repr_after_resolve(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(return_value=httpx.Response(200, json=make_release()))
        lazy = client.releases.get(400027)
        await lazy
        r = repr(lazy)
        assert "AsyncLazyResource" not in r

    async def test_error_raises(self, client, respx_mock):
        respx_mock.get("/releases/999").mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
        lazy = client.releases.get(999)
        with pytest.raises(NotFoundError):
            await lazy


class TestAttributeAccess:
    async def test_data_attr_before_await_raises(self, client):
        lazy = client.releases.get(400027)
        with pytest.raises(AttributeError, match="Cannot access 'title'"):
            lazy.title

    async def test_data_attr_after_await(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(return_value=httpx.Response(200, json=make_release()))
        lazy = client.releases.get(400027)
        await lazy
        assert lazy.title == "The Downward Spiral"


class TestGetItem:
    def test_getitem_before_await_raises(self, client):
        lazy = client.releases.get(400027)
        with pytest.raises(TypeError, match="Cannot subscript unresolved"):
            lazy["title"]

    async def test_getitem_after_await(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(return_value=httpx.Response(200, json=make_release()))
        lazy = client.releases.get(400027)
        await lazy
        # Pydantic models don't support subscript by default, so this should raise
        with pytest.raises(TypeError, match="not subscriptable"):
            lazy["title"]


class TestSubResources:
    def test_sub_resource_no_http(self, client, respx_mock):
        lazy = client.releases.get(400027)
        _rating = lazy.rating
        assert respx_mock.calls.call_count == 0

    def test_sub_resource_cached(self, client):
        lazy = client.releases.get(400027)
        r1 = lazy.rating
        r2 = lazy.rating
        assert r1 is r2

    def test_multiple_sub_resources(self, client, respx_mock):
        lazy = client.releases.get(400027)
        _ = lazy.rating
        _ = lazy.stats
        _ = lazy.price_suggestions
        _ = lazy.marketplace_stats
        assert respx_mock.calls.call_count == 0
