"""Tests for AsyncPage."""

from __future__ import annotations

import httpx
import pytest

from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._exceptions import DiscogsAPIError
from discogs_sdk.models.release import Release

from tests.conftest import BASE_URL, make_paginated_response, make_release


class TestSinglePage:
    async def test_iterates_all_items(self, client, respx_mock):
        items = [make_release(id=i, title=f"R{i}") for i in range(3)]
        respx_mock.get("/releases").mock(
            return_value=httpx.Response(200, json=make_paginated_response("releases", items))
        )
        page = AsyncPage(
            client=client,
            path="/releases",
            params={},
            model_cls=Release,
            items_key="releases",
        )
        results = [item async for item in page]
        assert len(results) == 3
        assert all(isinstance(r, Release) for r in results)

    async def test_stops_after_single_page(self, client, respx_mock):
        respx_mock.get("/releases").mock(
            return_value=httpx.Response(200, json=make_paginated_response("releases", [make_release()]))
        )
        page = AsyncPage(client=client, path="/releases", params={}, model_cls=Release, items_key="releases")
        results = [item async for item in page]
        assert len(results) == 1
        assert respx_mock.calls.call_count == 1


class TestMultiPage:
    async def test_follows_next_url(self, client, respx_mock):
        page1 = make_paginated_response(
            "releases",
            [make_release(id=1, title="R1")],
            page=1,
            pages=2,
            next_url=f"{BASE_URL}/releases?page=2",
        )
        page2 = make_paginated_response(
            "releases",
            [make_release(id=2, title="R2")],
            page=2,
            pages=2,
        )
        responses = iter(
            [
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )
        respx_mock.get("/releases").mock(side_effect=lambda req: next(responses))
        page = AsyncPage(client=client, path="/releases", params={}, model_cls=Release, items_key="releases")
        results = [item async for item in page]
        assert len(results) == 2
        assert results[0].id == 1
        assert results[1].id == 2


class TestEmptyPage:
    async def test_empty_yields_nothing(self, client, respx_mock):
        respx_mock.get("/releases").mock(return_value=httpx.Response(200, json=make_paginated_response("releases", [])))
        page = AsyncPage(client=client, path="/releases", params={}, model_cls=Release, items_key="releases")
        results = [item async for item in page]
        assert results == []


class TestEmptyNextPage:
    async def test_next_url_returns_empty_items(self, client, respx_mock):
        """When page 1 has a next_url but page 2 returns empty items, iteration stops."""
        page1 = make_paginated_response(
            "releases",
            [make_release(id=1, title="R1")],
            page=1,
            pages=2,
            next_url=f"{BASE_URL}/releases?page=2",
        )
        page2 = make_paginated_response("releases", [], page=2, pages=2)
        responses = iter(
            [
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )
        respx_mock.get("/releases").mock(side_effect=lambda req: next(responses))
        page = AsyncPage(client=client, path="/releases", params={}, model_cls=Release, items_key="releases")
        results = [item async for item in page]
        assert len(results) == 1
        assert results[0].id == 1


class TestItemsPath:
    async def test_nested_items_path(self, client, respx_mock):
        body = {
            "pagination": {"page": 1, "pages": 1, "urls": {}},
            "submissions": {"releases": [make_release(id=1), make_release(id=2)]},
        }
        respx_mock.get("/users/trent_reznor/submissions").mock(return_value=httpx.Response(200, json=body))
        page = AsyncPage(
            client=client,
            path="/users/trent_reznor/submissions",
            params={},
            model_cls=Release,
            items_key="submissions",
            items_path=["submissions", "releases"],
        )
        results = [item async for item in page]
        assert len(results) == 2

    async def test_missing_items_path_key(self, client, respx_mock):
        body = {"pagination": {"page": 1, "pages": 1, "urls": {}}}
        respx_mock.get("/users/trent_reznor/submissions").mock(return_value=httpx.Response(200, json=body))
        page = AsyncPage(
            client=client,
            path="/users/trent_reznor/submissions",
            params={},
            model_cls=Release,
            items_key="submissions",
            items_path=["submissions", "releases"],
        )
        results = [item async for item in page]
        assert results == []


class TestErrors:
    async def test_error_on_first_page(self, no_retry_client, respx_mock):
        respx_mock.get("/releases").mock(return_value=httpx.Response(500, json={"message": "Server Error"}))
        page = AsyncPage(client=no_retry_client, path="/releases", params={}, model_cls=Release, items_key="releases")
        with pytest.raises(DiscogsAPIError):
            async for _ in page:
                pass

    async def test_error_on_second_page(self, no_retry_client, respx_mock):
        page1 = make_paginated_response(
            "releases",
            [make_release(id=1, title="R1")],
            page=1,
            pages=2,
            next_url=f"{BASE_URL}/releases?page=2",
        )
        error_response = httpx.Response(500, json={"message": "Server Error"})
        responses = iter([httpx.Response(200, json=page1), error_response])
        respx_mock.get("/releases").mock(side_effect=lambda req: next(responses))
        page = AsyncPage(client=no_retry_client, path="/releases", params={}, model_cls=Release, items_key="releases")
        with pytest.raises(DiscogsAPIError):
            async for _ in page:
                pass


class TestCustomItemsKey:
    async def test_custom_key(self, client, respx_mock):
        respx_mock.get("/wants").mock(
            return_value=httpx.Response(
                200, json=make_paginated_response("wants", [{"id": 1, "basic_information": {"id": 1}}])
            )
        )
        from discogs_sdk.models.wantlist import Want

        page = AsyncPage(client=client, path="/wants", params={}, model_cls=Want, items_key="wants")
        results = [item async for item in page]
        assert len(results) == 1
