"""Tests for async Search resource."""

from __future__ import annotations

import pytest
import respx

from discogs_sdk import AsyncDiscogs
from discogs_sdk.models.search import SearchResult
from tests.conftest import (
    BASE_URL,
    make_paginated_response,
    make_search_result,
    mock_router,
)
from tests.documented_payloads import SEARCH_RESULT


class TestSearch:
    async def test_query_remapped_to_q(self, client, respx_mock):
        respx_mock.get("/database/search").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("results", [make_search_result()])
            )
        )
        results = [item async for item in client.search(query="nine inch nails")]
        assert len(results) == 1
        # Verify the request used 'q' param
        request = respx_mock.calls[0].request
        assert "q" in dict(request.url.params)

    async def test_none_values_filtered(self, client, respx_mock):
        respx_mock.get("/database/search").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("results", [make_search_result()])
            )
        )
        results = [item async for item in client.search(query="test", type=None)]
        assert len(results) == 1
        request = respx_mock.calls[0].request
        assert "type" not in dict(request.url.params)

    async def test_returns_search_results(self, client, respx_mock):
        items = [make_search_result(id=i, title=f"R{i}") for i in range(3)]
        respx_mock.get("/database/search").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("results", items)
            )
        )
        results = [item async for item in client.search(query="test")]
        assert len(results) == 3
        assert all(isinstance(r, SearchResult) for r in results)

    async def test_multi_page_pagination(self, client, respx_mock):
        search = f"{BASE_URL}/database/search"
        page_2_url = f"{search}?q=nine+inch+nails&page=2&per_page=1"
        page1 = make_paginated_response(
            "results",
            [make_search_result(id=1)],
            page=1,
            pages=2,
            next_url=page_2_url,
        )
        page2 = make_paginated_response(
            "results",
            [make_search_result(id=2)],
            page=2,
            pages=2,
        )
        responses = iter(
            [
                respx.MockResponse(200, json=page1),
                respx.MockResponse(200, json=page2),
            ]
        )
        route = respx_mock.get("/database/search").mock(
            side_effect=lambda req: next(responses)
        )
        results = [item async for item in client.search(query="nine inch nails")]
        assert [r.id for r in results] == [1, 2]
        assert [str(call.request.url) for call in route.calls] == [
            f"{search}?page=1&q=nine+inch+nails",
            page_2_url,
        ]

    async def test_additional_params(self, client, respx_mock):
        route = respx_mock.get("/database/search").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("results", [make_search_result()])
            )
        )
        results = [
            item
            async for item in client.search(query="test", type="release", year="1994")
        ]
        assert len(results) == 1
        params = route.calls.last.request.url.params
        assert params["q"] == "test"
        assert params["type"] == "release"
        assert params["year"] == "1994"

    async def test_next_link_is_rebased_onto_base_url(self):
        proxy = "https://proxy.example"
        bodies = [
            make_paginated_response(
                "results",
                [make_search_result(id=1)],
                page=1,
                pages=2,
                next_url=f"{BASE_URL}/database/search?q=Nine+Inch+Nails&page=2",
            ),
            make_paginated_response("results", [make_search_result(id=2)], page=2),
        ]
        with mock_router(base_url=None) as router:
            route = router.route().mock(
                side_effect=lambda req: respx.MockResponse(200, json=bodies.pop(0))
            )
            client = AsyncDiscogs(token="test-token", base_url=proxy)
            results = [item async for item in client.search(query="Nine Inch Nails")]

        assert len(results) == 2
        assert str(route.calls[1].request.url) == (
            f"{proxy}/database/search?q=Nine+Inch+Nails&page=2"
        )


class TestSearchResultModel:
    async def test_required_fields(self, client, respx_mock):
        respx_mock.get("/database/search").mock(
            return_value=respx.MockResponse(
                200,
                json=make_paginated_response("results", [{"id": 1, "title": "T"}]),
            )
        )
        results = [item async for item in client.search(query="t")]
        assert results[0].type is None

    async def test_extra_allow(self, client, respx_mock):
        respx_mock.get("/database/search").mock(
            return_value=respx.MockResponse(
                200,
                json=make_paginated_response(
                    "results", [{"id": 1, "title": "T", "_unknown_extra_field": "test"}]
                ),
            )
        )
        results = [item async for item in client.search(query="t")]
        assert results[0].model_extra["_unknown_extra_field"] == "test"


class TestSearchResultUri:
    async def _search_one(self, client, respx_mock, item):
        respx_mock.get("/database/search").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("results", [item])
            )
        )
        return await anext(client.search(query="t"))

    async def test_documented_relative_uri_is_made_absolute(self, client, respx_mock):
        result = await self._search_one(client, respx_mock, SEARCH_RESULT)
        assert result.uri == "https://www.discogs.com/release/352665"
        assert result.raw["uri"] == "/release/352665"

    async def test_percent_encoded_path_is_prefixed_unchanged(self, client, respx_mock):
        path = "/Nine-Inch-Nails-Ghosts-I%E2%80%93IV/release/352665"
        item = {**make_search_result(), "uri": path}
        result = await self._search_one(client, respx_mock, item)
        assert result.uri == f"https://www.discogs.com{path}"
        assert result.raw["uri"] == path

    @pytest.mark.parametrize(
        "uri",
        ["https://www.discogs.com/release/352665", None],
        ids=["absolute", "null"],
    )
    async def test_absolute_or_null_uri_is_unchanged(self, client, respx_mock, uri):
        item = {**make_search_result(), "uri": uri}
        result = await self._search_one(client, respx_mock, item)
        assert result.uri == uri

    async def test_missing_uri_stays_none(self, client, respx_mock):
        result = await self._search_one(client, respx_mock, make_search_result())
        assert result.uri is None

    async def test_round_trip_keeps_the_absolute_uri(self, client, respx_mock):
        result = await self._search_one(client, respx_mock, SEARCH_RESULT)
        restored = SearchResult.model_validate(result.model_dump())
        assert restored == result
        assert restored.uri == "https://www.discogs.com/release/352665"
