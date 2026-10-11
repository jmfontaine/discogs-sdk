"""Tests for LazyResource (sync auto-resolve on attribute access)."""

from __future__ import annotations

import contextlib
import copy

import pytest
import respx

from discogs_sdk._exceptions import NotFoundError
from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync.resources.artists import ArtistReleases
from discogs_sdk._sync.resources.releases import ReleaseRating, ReleaseStatsResource
from tests.conftest import make_release


class TestCreation:
    def test_no_http_on_creation(self, client, respx_mock):
        _lazy = client.releases.get(400027)
        assert respx_mock.calls.call_count == 0

    def test_no_await_method(self, client):
        assert not hasattr(LazyResource, "__await__")


class TestAutoResolve:
    def test_attribute_access_triggers_http(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        lazy = client.releases.get(400027)
        assert lazy.title == "The Downward Spiral"
        assert respx_mock.calls.call_count == 1

    def test_second_access_cached(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        lazy = client.releases.get(400027)
        _ = lazy.title
        _ = lazy.year
        assert respx_mock.calls.call_count == 1

    def test_error_raises(self, client, respx_mock):
        respx_mock.get("/releases/999").mock(
            return_value=respx.MockResponse(404, json={"message": "Not Found"})
        )
        lazy = client.releases.get(999)
        with pytest.raises(NotFoundError):
            _ = lazy.title


class TestPrivateNameProbes:
    """Tools probe proxies for ``_``-prefixed names; none of them is a data field.

    The zero-request tests register no route: respx rejects any request to an
    unmocked URL, so a probe that reached the network fails the test.
    """

    def test_probes_send_no_request(self, client, respx_mock):
        lazy = client.releases.get(400027)
        assert getattr(lazy, "_repr_html_", None) is None
        assert not hasattr(lazy, "__html__")
        assert not hasattr(lazy, "__deepcopy__")
        assert respx_mock.calls.call_count == 0

    def test_deepcopy_sends_no_request(self, client, respx_mock):
        lazy = client.releases.get(400027)
        # Whether a proxy can be deep-copied is out of scope: its client holds a
        # lock, which deepcopy rejects. Only the absence of a request is asserted.
        with contextlib.suppress(TypeError):
            copy.deepcopy(lazy)
        assert respx_mock.calls.call_count == 0

    def test_probes_are_not_delegated_after_resolution(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        lazy = client.releases.get(400027)
        assert lazy.title == "The Downward Spiral"
        # The resolved Release defines __deepcopy__; the proxy still does not.
        assert not hasattr(lazy, "__deepcopy__")
        assert getattr(lazy, "_repr_html_", None) is None
        assert respx_mock.calls.call_count == 1


class TestGetItem:
    def test_getitem_resolves_and_raises_not_subscriptable(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
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


class TestReadOnly:
    def test_field_assignment_raises_before_any_request(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        lazy = client.releases.get(400027)
        with pytest.raises(AttributeError, match="'title'.*read-only"):
            lazy.title = "x"
        assert respx_mock.calls.call_count == 0
        assert lazy.title == "The Downward Spiral"
        assert respx_mock.calls.call_count == 1

    def test_field_assignment_raises_after_resolution(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        lazy = client.releases.get(400027)
        _ = lazy.title
        with pytest.raises(AttributeError, match="'title'.*read-only"):
            lazy.title = "x"
        assert lazy.title == "The Downward Spiral"

    def test_sub_resource_assignment_raises(self, client):
        artist = client.artists.get(3857)
        with pytest.raises(AttributeError, match="'releases'.*read-only"):
            artist.releases = None
        release = client.releases.get(400027)
        rating = release.rating
        with pytest.raises(AttributeError, match="'rating'.*read-only"):
            release.rating = None
        assert release.rating is rating


class TestRepr:
    def test_repr_before_resolve(self, client):
        lazy = client.releases.get(400027)
        r = repr(lazy)
        assert "LazyResource" in r
        assert "Release" in r

    def test_repr_after_resolve(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        lazy = client.releases.get(400027)
        _ = lazy.title  # triggers resolve
        r = repr(lazy)
        assert "LazyResource" not in r


class TestTypedSurface:
    def test_attribute_access_resolves_the_model(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        resolved = client.releases.get(400027)
        assert resolved.title == "The Downward Spiral"

    def test_sub_resources_are_concrete_resources(self, client, respx_mock):
        lazy = client.releases.get(400027)
        assert isinstance(lazy.rating, ReleaseRating)
        assert isinstance(lazy.stats, ReleaseStatsResource)
        assert isinstance(client.artists.get(3857).releases, ArtistReleases)
        assert respx_mock.calls.call_count == 0

    def test_deep_navigation_makes_no_request(self, client, respx_mock):
        instance = (
            client.users.get("trent_reznor")
            .collection.folders.get(1)
            .releases.get(352665)
            .instances.get(20)
        )
        assert instance.fields is not None
        assert respx_mock.calls.call_count == 0
