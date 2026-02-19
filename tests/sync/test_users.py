"""Tests for sync Users resource."""

from __future__ import annotations

import httpx

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
        respx_mock.get("/users/trent_reznor").mock(return_value=httpx.Response(200, json=make_user()))
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
        respx_mock.post("/users/trent_reznor").mock(return_value=httpx.Response(200, json=make_user()))
        lazy = client.users.get("trent_reznor")
        result = lazy.update(name="New Name", location="NYC")
        assert isinstance(result, User)

    def test_update_only_non_none(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor").mock(return_value=httpx.Response(200, json=make_user()))
        lazy = client.users.get("trent_reznor")
        lazy.update(name="X")
        body = respx_mock.calls[0].request.content
        assert b"name" in body
        assert b"home_page" not in body

    def test_update_all_fields(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor").mock(return_value=httpx.Response(200, json=make_user()))
        lazy = client.users.get("trent_reznor")
        lazy.update(name="NIN", home_page="https://nin.com", location="LA", curr_abbr="USD")
        body = respx_mock.calls[0].request.content
        assert b"home_page" in body
        assert b"curr_abbr" in body


class TestUserSubmissions:
    def test_submissions_uses_items_path(self, client, respx_mock):
        body = {
            "pagination": {"page": 1, "pages": 1, "urls": {}},
            "submissions": {"releases": [make_release(id=1), make_release(id=2)]},
        }
        respx_mock.get("/users/trent_reznor/submissions").mock(return_value=httpx.Response(200, json=body))
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
        respx_mock.get("/users/trent_reznor/submissions").mock(return_value=httpx.Response(200, json=body))
        lazy = client.users.get("trent_reznor")
        results = list(lazy.submissions.artists.list())
        assert len(results) == 2
        assert all(isinstance(a, Artist) for a in results)

    def test_submissions_labels(self, client, respx_mock):
        body = {
            "pagination": {"page": 1, "pages": 1, "urls": {}},
            "submissions": {"labels": [make_label(id=1), make_label(id=2)]},
        }
        respx_mock.get("/users/trent_reznor/submissions").mock(return_value=httpx.Response(200, json=body))
        lazy = client.users.get("trent_reznor")
        results = list(lazy.submissions.labels.list())
        assert len(results) == 2
        assert all(isinstance(item, Label) for item in results)


class TestUserContributions:
    def test_contributions_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/contributions").mock(
            return_value=httpx.Response(200, json=make_paginated_response("contributions", [make_release()]))
        )
        lazy = client.users.get("trent_reznor")
        results = list(lazy.contributions.list(sort="label", sort_order="asc"))
        assert len(results) == 1
        assert isinstance(results[0], Release)
        assert results[0].year == 1994


class TestUserInventory:
    def test_inventory_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/inventory").mock(
            return_value=httpx.Response(200, json=make_paginated_response("listings", [make_listing()]))
        )
        lazy = client.users.get("trent_reznor")
        results = list(lazy.inventory.list(sort="price"))
        assert len(results) == 1
        assert isinstance(results[0], Listing)


class TestUserNamespace:
    def test_identity(self, client, respx_mock):
        respx_mock.get("/oauth/identity").mock(return_value=httpx.Response(200, json=make_identity()))
        result = client.user.identity()
        assert isinstance(result, Identity)
        assert result.username == "trent_reznor"


class TestUserModel:
    def test_required_fields(self, client, respx_mock):
        respx_mock.get("/users/x").mock(return_value=httpx.Response(200, json={"id": 1, "username": "x"}))
        lazy = client.users.get("x")
        assert lazy.name is None

    def test_extra_allow(self, client, respx_mock):
        respx_mock.get("/users/x").mock(
            return_value=httpx.Response(200, json={"id": 1, "username": "x", "_unknown_extra_field": "test"})
        )
        lazy = client.users.get("x")
        assert lazy.model_extra["_unknown_extra_field"] == "test"
