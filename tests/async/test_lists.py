"""Tests for async Lists resource."""

from __future__ import annotations

import httpx

from discogs_sdk.models.list_ import List_, ListSummary

from tests.conftest import make_list, make_list_summary, make_paginated_response


class TestListsGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.lists.get(1)
        assert respx_mock.calls.call_count == 0

    async def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/lists/1").mock(return_value=httpx.Response(200, json=make_list()))
        result = await client.lists.get(1)
        assert isinstance(result, List_)
        assert result.name == "Industrial Essentials"
        assert len(result.items) == 1


class TestUserLists:
    async def test_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/lists").mock(
            return_value=httpx.Response(200, json=make_paginated_response("lists", [make_list_summary()]))
        )
        lazy = client.users.get("trent_reznor")
        results = [item async for item in lazy.lists.list()]
        assert len(results) == 1
        assert isinstance(results[0], ListSummary)
        assert results[0].name == "Industrial Essentials"


class TestListModel:
    async def test_required_fields(self, client, respx_mock):
        respx_mock.get("/lists/1").mock(return_value=httpx.Response(200, json={"id": 1, "name": "L"}))
        result = await client.lists.get(1)
        assert result.items is None

    async def test_extra_allow(self, client, respx_mock):
        respx_mock.get("/lists/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "name": "L", "uri": "http://x"})
        )
        result = await client.lists.get(1)
        assert result.model_extra["uri"] == "http://x"
