"""Tests for LazyResource (sync auto-resolve on attribute access)."""

from __future__ import annotations

import httpx
import pytest

from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._exceptions import NotFoundError

from tests.conftest import make_release


class TestCreation:
    def test_no_http_on_creation(self, client, respx_mock):
        _lazy = client.releases.get(400027)
        assert respx_mock.calls.call_count == 0

    def test_no_await_method(self, client):
        assert not hasattr(LazyResource, "__await__")


class TestAutoResolve:
    def test_attribute_access_triggers_http(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(return_value=httpx.Response(200, json=make_release()))
        lazy = client.releases.get(400027)
        assert lazy.title == "The Downward Spiral"
        assert respx_mock.calls.call_count == 1

    def test_second_access_cached(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(return_value=httpx.Response(200, json=make_release()))
        lazy = client.releases.get(400027)
        _ = lazy.title
        _ = lazy.year
        assert respx_mock.calls.call_count == 1

    def test_error_raises(self, client, respx_mock):
        respx_mock.get("/releases/999").mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
        lazy = client.releases.get(999)
        with pytest.raises(NotFoundError):
            lazy.title


class TestGetItem:
    def test_getitem_resolves_and_raises_not_subscriptable(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(return_value=httpx.Response(200, json=make_release()))
        lazy = client.releases.get(400027)
        # Pydantic models don't support subscript by default
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


class TestRepr:
    def test_repr_before_resolve(self, client):
        lazy = client.releases.get(400027)
        r = repr(lazy)
        assert "LazyResource" in r
        assert "Release" in r

    def test_repr_after_resolve(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(return_value=httpx.Response(200, json=make_release()))
        lazy = client.releases.get(400027)
        _ = lazy.title  # triggers resolve
        r = repr(lazy)
        assert "LazyResource" not in r
