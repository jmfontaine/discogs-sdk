"""Tests for sync Lists resource."""

from __future__ import annotations

import respx

from discogs_sdk.models.list_ import ListSummary
from tests.conftest import make_list, make_list_summary, make_paginated_response


class TestListsGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.lists.get(1)
        assert respx_mock.calls.call_count == 0

    def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/lists/1").mock(return_value=respx.MockResponse(200, json=make_list()))
        lazy = client.lists.get(1)
        assert lazy.id == 1  # the detail response spells this "list_id"
        assert lazy.name == "Industrial Essentials"
        assert len(lazy.items) == 1

    def test_canonical_id_still_accepted(self, client, respx_mock):
        respx_mock.get("/lists/1").mock(return_value=respx.MockResponse(200, json={"id": 1, "name": "L"}))
        assert client.lists.get(1).id == 1


class TestUserLists:
    def test_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/lists").mock(
            return_value=respx.MockResponse(200, json=make_paginated_response("lists", [make_list_summary()]))
        )
        lazy = client.users.get("trent_reznor")
        results = list(lazy.lists.list())
        assert len(results) == 1
        assert isinstance(results[0], ListSummary)
        assert results[0].name == "Industrial Essentials"
