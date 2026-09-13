"""Tests for SyncPage."""

from __future__ import annotations

import pytest
import respx

from discogs_sdk._exceptions import DiscogsAPIError
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk.models.release import Release
from tests.conftest import BASE_URL, make_paginated_response, make_release


class TestSinglePage:
    def test_iterates_all_items(self, client, respx_mock):
        items = [make_release(id=i, title=f"R{i}") for i in range(3)]
        respx_mock.get("/releases").mock(
            return_value=respx.MockResponse(200, json=make_paginated_response("releases", items))
        )
        page = SyncPage(client=client, path="/releases", params={}, model_cls=Release, items_key="releases")
        results = list(page)
        assert len(results) == 3
        assert all(isinstance(r, Release) for r in results)

    def test_stops_with_stop_iteration(self, client, respx_mock):
        respx_mock.get("/releases").mock(
            return_value=respx.MockResponse(200, json=make_paginated_response("releases", [make_release()]))
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
                respx.MockResponse(200, json=page1),
                respx.MockResponse(200, json=page2),
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
                respx.MockResponse(200, json=page1),
                respx.MockResponse(200, json=page2),
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
        respx_mock.get("/users/trent_reznor/submissions").mock(return_value=respx.MockResponse(200, json=body))
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
            return_value=respx.MockResponse(
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
        responses = iter([respx.MockResponse(200, json=page1), respx.MockResponse(200, json=page2)])
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
            return_value=respx.MockResponse(
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
            return_value=respx.MockResponse(
                200, json=make_paginated_response("releases", [make_release()], per_page=10)
            )
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
        respx_mock.get("/releases").mock(return_value=respx.MockResponse(500, json={"message": "Server Error"}))
        page = SyncPage(client=no_retry_client, path="/releases", params={}, model_cls=Release, items_key="releases")
        with pytest.raises(DiscogsAPIError):
            list(page)


def _submissions_page(page: int, pages: int, *, releases: list[dict], artists: list[dict] | None = None) -> dict:
    body: dict = {
        "pagination": {"page": page, "pages": pages, "per_page": 50, "items": 2, "urls": {}},
        "submissions": {"releases": releases, "artists": artists or []},
    }
    if page < pages:
        body["pagination"]["urls"]["next"] = f"{BASE_URL}/users/trent_reznor/submissions?page={page + 1}"
    return body


class TestEmptySelectedCategories:
    """An empty selected category must not truncate iteration."""

    def test_continues_past_an_empty_middle_page(self, client, respx_mock):
        pages = [
            _submissions_page(1, 3, releases=[make_release(id=1, title="Pretty Hate Machine")]),
            _submissions_page(2, 3, releases=[], artists=[{"id": 3857, "name": "Nine Inch Nails"}]),
            _submissions_page(3, 3, releases=[make_release(id=2, title="The Downward Spiral")]),
        ]
        responses = iter(pages)
        route = respx_mock.get("/users/trent_reznor/submissions").mock(
            side_effect=lambda req: respx.MockResponse(200, json=next(responses))
        )

        titles = [item.title for item in client.users.get("trent_reznor").submissions.list()]

        assert titles == ["Pretty Hate Machine", "The Downward Spiral"]
        assert route.call_count == 3

    def test_continues_past_consecutive_empty_pages(self, client, respx_mock):
        pages = [
            _submissions_page(1, 4, releases=[]),
            _submissions_page(2, 4, releases=[]),
            _submissions_page(3, 4, releases=[]),
            _submissions_page(4, 4, releases=[make_release(id=2, title="The Fragile")]),
        ]
        responses = iter(pages)
        route = respx_mock.get("/users/trent_reznor/submissions").mock(
            side_effect=lambda req: respx.MockResponse(200, json=next(responses))
        )

        titles = [item.title for item in client.users.get("trent_reznor").submissions.list()]

        assert titles == ["The Fragile"]
        assert route.call_count == 4

    def test_empty_final_page_terminates_and_stays_exhausted(self, client, respx_mock):
        pages = [
            _submissions_page(1, 2, releases=[make_release(id=1, title="Broken")]),
            _submissions_page(2, 2, releases=[]),
        ]
        responses = iter(pages)
        route = respx_mock.get("/users/trent_reznor/submissions").mock(
            side_effect=lambda req: respx.MockResponse(200, json=next(responses))
        )

        page = client.users.get("trent_reznor").submissions.list()
        assert [item.title for item in page] == ["Broken"]
        assert route.call_count == 2

        with pytest.raises(StopIteration):
            page.__next__()
        assert route.call_count == 2

    def test_failure_on_a_later_page_propagates(self, no_retry_client, respx_mock):
        responses = iter(
            [
                respx.MockResponse(200, json=_submissions_page(1, 3, releases=[])),
                respx.MockResponse(502, html="<html>Bad Gateway</html>"),
            ]
        )
        respx_mock.get("/users/trent_reznor/submissions").mock(side_effect=lambda req: next(responses))

        with pytest.raises(DiscogsAPIError) as exc_info:
            _ = list(no_retry_client.users.get("trent_reznor").submissions.list())

        # Truncation would have looked like success.
        assert exc_info.value.status_code == 502
