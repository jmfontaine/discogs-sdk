"""Tests for sync Users resource."""

from __future__ import annotations

import json

import pytest
import respx

from discogs_sdk import Discogs
from discogs_sdk._cache import MemoryCache
from discogs_sdk.models.artist import Artist
from discogs_sdk.models.label import Label
from discogs_sdk.models.marketplace import Listing
from discogs_sdk.models.release import Release
from discogs_sdk.models.user import Identity, User
from tests.conftest import (
    make_artist,
    make_identity,
    make_label,
    make_listing,
    make_paginated_response,
    make_release,
    make_user,
)


class TestUsersGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.users.get("trent_reznor")
        assert respx_mock.calls.call_count == 0

    def test_get_resolves_to_user(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor").mock(
            return_value=respx.MockResponse(200, json=make_user())
        )
        lazy = client.users.get("trent_reznor")
        assert lazy.username == "trent_reznor"


class TestUserSubResources:
    def test_all_sub_resources_no_http(self, client, respx_mock):
        lazy = client.users.get("trent_reznor")
        _ = lazy.update
        _ = lazy.submissions
        _ = lazy.contributions
        _ = lazy.inventory
        _ = lazy.wantlist
        _ = lazy.lists
        _ = lazy.collection
        assert respx_mock.calls.call_count == 0


class TestUserUpdate:
    def test_update_with_fields(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor").mock(
            return_value=respx.MockResponse(200, json=make_user())
        )
        lazy = client.users.get("trent_reznor")
        result = lazy.update(name="New Name", location="NYC")
        assert isinstance(result, User)

    def test_omitted_fields_are_not_sent(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor").mock(
            return_value=respx.MockResponse(200, json=make_user())
        )
        client.users.get("trent_reznor").update(name="X")
        payload = json.loads(respx_mock.calls[0].request.content)
        assert payload == {"name": "X"}

    def test_every_documented_field_is_sent(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor").mock(
            return_value=respx.MockResponse(200, json=make_user())
        )
        client.users.get("trent_reznor").update(
            name="Trent Reznor",
            home_page="https://www.nin.com",
            location="Cleveland",
            profile="Founder of Nine Inch Nails.",
            curr_abbr="USD",
        )
        payload = json.loads(respx_mock.calls[0].request.content)
        assert payload == {
            "name": "Trent Reznor",
            "home_page": "https://www.nin.com",
            "location": "Cleveland",
            "profile": "Founder of Nine Inch Nails.",
            "curr_abbr": "USD",
        }

    def test_empty_profile_clears_the_biography(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor").mock(
            return_value=respx.MockResponse(200, json=make_user())
        )
        client.users.get("trent_reznor").update(profile="")
        payload = json.loads(respx_mock.calls[0].request.content)
        assert payload == {"profile": ""}


class TestUserSubmissions:
    def test_submissions_uses_items_path(self, client, respx_mock):
        body = {
            "pagination": {"page": 1, "pages": 1, "urls": {}},
            "submissions": {"releases": [make_release(id=1), make_release(id=2)]},
        }
        respx_mock.get("/users/trent_reznor/submissions").mock(
            return_value=respx.MockResponse(200, json=body)
        )
        lazy = client.users.get("trent_reznor")
        results = list(lazy.submissions.list())
        assert len(results) == 2
        assert all(isinstance(s, Release) for s in results)
        assert results[0].year == 1994

    def test_submissions_artists(self, client, respx_mock):
        body = {
            "pagination": {"page": 1, "pages": 1, "urls": {}},
            "submissions": {"artists": [make_artist(id=1), make_artist(id=2)]},
        }
        respx_mock.get("/users/trent_reznor/submissions").mock(
            return_value=respx.MockResponse(200, json=body)
        )
        lazy = client.users.get("trent_reznor")
        results = list(lazy.submissions.artists.list())
        assert len(results) == 2
        assert all(isinstance(a, Artist) for a in results)

    def test_submissions_labels(self, client, respx_mock):
        body = {
            "pagination": {"page": 1, "pages": 1, "urls": {}},
            "submissions": {"labels": [make_label(id=1), make_label(id=2)]},
        }
        respx_mock.get("/users/trent_reznor/submissions").mock(
            return_value=respx.MockResponse(200, json=body)
        )
        lazy = client.users.get("trent_reznor")
        results = list(lazy.submissions.labels.list())
        assert len(results) == 2
        assert all(isinstance(item, Label) for item in results)


class TestUserContributions:
    def test_contributions_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/contributions").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("contributions", [make_release()])
            )
        )
        lazy = client.users.get("trent_reznor")
        results = list(lazy.contributions.list(sort="label", sort_order="asc"))
        assert len(results) == 1
        assert isinstance(results[0], Release)
        assert results[0].year == 1994


class TestUserInventory:
    def test_inventory_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/inventory").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("listings", [make_listing()])
            )
        )
        lazy = client.users.get("trent_reznor")
        results = list(lazy.inventory.list(sort="price"))
        assert len(results) == 1
        assert isinstance(results[0], Listing)


class TestUserNamespace:
    def test_identity(self, client, respx_mock):
        respx_mock.get("/oauth/identity").mock(
            return_value=respx.MockResponse(200, json=make_identity())
        )
        result = client.user.identity()
        assert isinstance(result, Identity)
        assert result.username == "trent_reznor"


class TestUserModel:
    def test_required_fields(self, client, respx_mock):
        respx_mock.get("/users/x").mock(
            return_value=respx.MockResponse(200, json={"id": 1, "username": "x"})
        )
        lazy = client.users.get("x")
        assert lazy.name is None

    def test_extra_allow(self, client, respx_mock):
        respx_mock.get("/users/x").mock(
            return_value=respx.MockResponse(
                200, json={"id": 1, "username": "x", "_unknown_extra_field": "test"}
            )
        )
        lazy = client.users.get("x")
        assert lazy.model_extra["_unknown_extra_field"] == "test"


HOSTILE = "a/b?c#d"
ENCODED = b"a%2Fb%3Fc%23d"
EMPTY_PAGE = {"pagination": {"page": 1, "pages": 1, "urls": {}}}


class TestUsernamePathEncoding:
    """A username is one path segment: its characters never act as URL syntax."""

    def test_get_encodes_username(self, client, respx_mock):
        route = respx_mock.route().respond(200, json=make_user())
        _ = client.users.get(HOSTILE).username
        assert route.calls.last.request.url.raw_path == b"/users/a%2Fb%3Fc%23d"

    def test_update_encodes_username(self, client, respx_mock):
        route = respx_mock.route().respond(200, json=make_user())
        client.users.get(HOSTILE).update(name="X")
        request = route.calls.last.request
        assert request.method == "POST"
        assert request.url.raw_path == b"/users/a%2Fb%3Fc%23d"

    @pytest.mark.parametrize(
        ("pages", "suffix"),
        [
            (lambda user: user.submissions.list(), b"/submissions"),
            (lambda user: user.submissions.artists.list(), b"/submissions"),
            (lambda user: user.submissions.labels.list(), b"/submissions"),
            (lambda user: user.contributions.list(), b"/contributions"),
            (lambda user: user.inventory.list(), b"/inventory"),
        ],
        ids=["submissions", "artists", "labels", "contributions", "inventory"],
    )
    def test_sub_resources_encode_username_once(
        self, client, respx_mock, pages, suffix
    ):
        route = respx_mock.route().respond(200, json=EMPTY_PAGE)
        _ = list(pages(client.users.get(HOSTILE)))
        path = route.calls.last.request.url.raw_path.partition(b"?")[0]
        assert path == b"/users/" + ENCODED + suffix
        assert b"%25" not in path

    @pytest.mark.parametrize("username", [".", ".."])
    def test_dot_segment_username_is_rejected(self, client, respx_mock, username):
        with pytest.raises(ValueError, match="path segment"):
            client.users.get(username)
        assert respx_mock.calls.call_count == 0

    def test_cache_key_holds_the_encoded_url(self, respx_mock):
        respx_mock.route().respond(200, json=make_user())
        cache = MemoryCache(ttl=600)
        client = Discogs(token="test-token", cache=cache)
        _ = client.users.get("a/b").username
        client.close()
        [key] = cache._store
        assert "/users/a%2Fb" in key
        assert "/users/a/b" not in key
