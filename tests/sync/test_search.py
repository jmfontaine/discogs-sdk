"""Tests for sync Search resource."""

from __future__ import annotations

import httpx

from discogs_sdk.models.search import SearchResult

from tests.conftest import BASE_URL, make_paginated_response, make_search_result


class TestSearch:
    def test_query_remapped_to_q(self, client, respx_mock):
        respx_mock.get("/database/search").mock(
            return_value=httpx.Response(200, json=make_paginated_response("results", [make_search_result()]))
        )
        results = list(client.search(query="nine inch nails"))
        assert len(results) == 1
        request = respx_mock.calls[0].request
        assert "q" in dict(request.url.params)

    def test_none_values_filtered(self, client, respx_mock):
        respx_mock.get("/database/search").mock(
            return_value=httpx.Response(200, json=make_paginated_response("results", [make_search_result()]))
        )
        results = list(client.search(query="test", type=None))
        assert len(results) == 1
        request = respx_mock.calls[0].request
        assert "type" not in dict(request.url.params)

    def test_returns_search_results(self, client, respx_mock):
        items = [make_search_result(id=i, title=f"R{i}") for i in range(3)]
        respx_mock.get("/database/search").mock(
            return_value=httpx.Response(200, json=make_paginated_response("results", items))
        )
        results = list(client.search(query="test"))
        assert len(results) == 3
        assert all(isinstance(r, SearchResult) for r in results)

    def test_multi_page_pagination(self, client, respx_mock):
        page1 = make_paginated_response(
            "results",
            [make_search_result(id=1)],
            page=1,
            pages=2,
            next_url=f"{BASE_URL}/database/search?q=test&page=2",
        )
        page2 = make_paginated_response(
            "results",
            [make_search_result(id=2)],
            page=2,
            pages=2,
        )
        responses = iter(
            [
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )
        respx_mock.get("/database/search").mock(side_effect=lambda req: next(responses))
        results = list(client.search(query="test"))
        assert len(results) == 2
