"""Tests for SyncPage."""

from __future__ import annotations

import httpx
import pytest

from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._exceptions import DiscogsAPIError
from discogs_sdk.models.release import Release

from tests.conftest import BASE_URL, make_paginated_response, make_release


class TestSinglePage:
    def test_iterates_all_items(self, client, respx_mock):
        items = [make_release(id=i, title=f"R{i}") for i in range(3)]
        respx_mock.get("/releases").mock(
            return_value=httpx.Response(200, json=make_paginated_response("releases", items))
        )
        page = SyncPage(client=client, path="/releases", params={}, model_cls=Release, items_key="releases")
        results = list(page)
        assert len(results) == 3
        assert all(isinstance(r, Release) for r in results)

    def test_stops_with_stop_iteration(self, client, respx_mock):
        respx_mock.get("/releases").mock(
            return_value=httpx.Response(200, json=make_paginated_response("releases", [make_release()]))
        )
        page = SyncPage(client=client, path="/releases", params={}, model_cls=Release, items_key="releases")
        results = list(page)
        assert len(results) == 1


class TestMultiPage:
    def test_follows_next_url(self, client, respx_mock):
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
        page = SyncPage(client=client, path="/releases", params={}, model_cls=Release, items_key="releases")
        results = list(page)
        assert len(results) == 2
        assert results[0].id == 1
        assert results[1].id == 2


class TestEmptyNextPage:
    def test_next_url_returns_empty_items(self, client, respx_mock):
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
        page = SyncPage(client=client, path="/releases", params={}, model_cls=Release, items_key="releases")
        results = list(page)
        assert len(results) == 1
        assert results[0].id == 1


class TestItemsPath:
    def test_nested_items_path(self, client, respx_mock):
        body = {
            "pagination": {"page": 1, "pages": 1, "urls": {}},
            "submissions": {"releases": [make_release(id=1), make_release(id=2)]},
        }
        respx_mock.get("/users/trent_reznor/submissions").mock(return_value=httpx.Response(200, json=body))
        page = SyncPage(
            client=client,
            path="/users/trent_reznor/submissions",
            params={},
            model_cls=Release,
            items_key="submissions",
            items_path=["submissions", "releases"],
        )
        results = list(page)
        assert len(results) == 2


class TestPaginationMetadata:
    def test_none_before_fetch(self, client):
        page = SyncPage(client=client, path="/releases", params={}, model_cls=Release, items_key="releases")
        assert page.page is None
        assert page.total_pages is None
        assert page.total_items is None
        assert page.per_page is None

    def test_populated_after_first_iteration(self, client, respx_mock):
        respx_mock.get("/releases").mock(
            return_value=httpx.Response(
                200,
                json=make_paginated_response(
                    "releases", [make_release()], page=1, pages=3, per_page=25, total_items=75
                ),
            )
        )
        page = SyncPage(client=client, path="/releases", params={}, model_cls=Release, items_key="releases")
        next(iter(page))
        assert page.page == 1
        assert page.total_pages == 3
        assert page.total_items == 75
        assert page.per_page == 25

    def test_updates_across_pages(self, client, respx_mock):
        page1 = make_paginated_response(
            "releases",
            [make_release(id=1)],
            page=1,
            pages=2,
            per_page=1,
            total_items=2,
            next_url=f"{BASE_URL}/releases?page=2",
        )
        page2 = make_paginated_response(
            "releases",
            [make_release(id=2)],
            page=2,
            pages=2,
            per_page=1,
            total_items=2,
        )
        responses = iter([httpx.Response(200, json=page1), httpx.Response(200, json=page2)])
        respx_mock.get("/releases").mock(side_effect=lambda req: next(responses))
        page = SyncPage(client=client, path="/releases", params={}, model_cls=Release, items_key="releases")
        results = list(page)
        assert len(results) == 2
        assert page.page == 2
        assert page.total_pages == 2
        assert page.total_items == 2
        assert page.per_page == 1


class TestPageParam:
    def test_page_overrides_default(self, client, respx_mock):
        """When page is passed in params, it overrides the default page=1."""
        respx_mock.get("/releases").mock(
            return_value=httpx.Response(
                200, json=make_paginated_response("releases", [make_release()], page=3, pages=5)
            )
        )
        page = SyncPage(client=client, path="/releases", params={"page": 3}, model_cls=Release, items_key="releases")
        next(iter(page))
        assert page.page == 3
        request = respx_mock.calls.last.request
        assert request.url.params["page"] == "3"

    def test_per_page_passed_through(self, client, respx_mock):
        """per_page param is sent to the API."""
        respx_mock.get("/releases").mock(
            return_value=httpx.Response(200, json=make_paginated_response("releases", [make_release()], per_page=10))
        )
        page = SyncPage(
            client=client, path="/releases", params={"per_page": 10}, model_cls=Release, items_key="releases"
        )
        next(iter(page))
        assert page.per_page == 10
        request = respx_mock.calls.last.request
        assert request.url.params["per_page"] == "10"


class TestErrors:
    def test_error_on_first_page(self, no_retry_client, respx_mock):
        respx_mock.get("/releases").mock(return_value=httpx.Response(500, json={"message": "Server Error"}))
        page = SyncPage(client=no_retry_client, path="/releases", params={}, model_cls=Release, items_key="releases")
        with pytest.raises(DiscogsAPIError):
            list(page)
