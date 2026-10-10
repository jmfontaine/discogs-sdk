"""Tests for SyncPage."""

from __future__ import annotations

import re

import pytest
import respx

from discogs_sdk import Discogs
from discogs_sdk._exceptions import DiscogsAPIError, DiscogsError
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk.models.release import Release
from tests.conftest import BASE_URL, make_paginated_response, make_release


class TestSinglePage:
    def test_iterates_all_items(self, client, respx_mock):
        items = [make_release(id=i, title=f"R{i}") for i in range(3)]
        respx_mock.get("/releases").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("releases", items)
            )
        )
        page = SyncPage(
            client=client,
            path="/releases",
            params={},
            model_cls=Release,
            items_key="releases",
        )
        results = list(page)
        assert len(results) == 3
        assert all(isinstance(r, Release) for r in results)

    def test_stops_with_stop_iteration(self, client, respx_mock):
        respx_mock.get("/releases").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("releases", [make_release()])
            )
        )
        page = SyncPage(
            client=client,
            path="/releases",
            params={},
            model_cls=Release,
            items_key="releases",
        )
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
        page = SyncPage(
            client=client,
            path="/releases",
            params={},
            model_cls=Release,
            items_key="releases",
        )
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
        page = SyncPage(
            client=client,
            path="/releases",
            params={},
            model_cls=Release,
            items_key="releases",
        )
        results = list(page)
        assert len(results) == 1
        assert results[0].id == 1


class TestItemsPath:
    def test_nested_items_path(self, client, respx_mock):
        body = {
            "pagination": {"page": 1, "pages": 1, "urls": {}},
            "submissions": {"releases": [make_release(id=1), make_release(id=2)]},
        }
        respx_mock.get("/users/trent_reznor/submissions").mock(
            return_value=respx.MockResponse(200, json=body)
        )
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
        page = SyncPage(
            client=client,
            path="/releases",
            params={},
            model_cls=Release,
            items_key="releases",
        )
        assert page.page is None
        assert page.total_pages is None
        assert page.total_items is None
        assert page.per_page is None

    def test_populated_after_first_iteration(self, client, respx_mock):
        respx_mock.get("/releases").mock(
            return_value=respx.MockResponse(
                200,
                json=make_paginated_response(
                    "releases",
                    [make_release()],
                    page=1,
                    pages=3,
                    per_page=25,
                    total_items=75,
                ),
            )
        )
        page = SyncPage(
            client=client,
            path="/releases",
            params={},
            model_cls=Release,
            items_key="releases",
        )
        next(iter(page))
        assert page.page == 1
        assert page.total_pages == 3
        assert page.total_items == 75
        assert page.per_page == 25

    def test_exposes_every_documented_url(self, client, respx_mock):
        body = make_paginated_response("releases", [make_release()])
        body["pagination"]["urls"] = {
            "first": f"{BASE_URL}/releases?page=1",
            "prev": f"{BASE_URL}/releases?page=1",
            "next": f"{BASE_URL}/releases?page=3",
            "last": f"{BASE_URL}/releases?page=30",
        }
        respx_mock.get("/releases").mock(
            return_value=respx.MockResponse(200, json=body)
        )
        page = SyncPage(
            client=client,
            path="/releases",
            params={},
            model_cls=Release,
            items_key="releases",
        )
        next(iter(page))
        assert page.first_url == f"{BASE_URL}/releases?page=1"
        assert page.prev_url == f"{BASE_URL}/releases?page=1"
        assert page.next_url == f"{BASE_URL}/releases?page=3"
        assert page.last_url == f"{BASE_URL}/releases?page=30"

    def test_urls_are_none_on_a_single_page(self, client, respx_mock):
        respx_mock.get("/releases").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("releases", [make_release()])
            )
        )
        page = SyncPage(
            client=client,
            path="/releases",
            params={},
            model_cls=Release,
            items_key="releases",
        )
        next(iter(page))
        assert page.first_url is None
        assert page.prev_url is None
        assert page.next_url is None
        assert page.last_url is None

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
        responses = iter(
            [respx.MockResponse(200, json=page1), respx.MockResponse(200, json=page2)]
        )
        respx_mock.get("/releases").mock(side_effect=lambda req: next(responses))
        page = SyncPage(
            client=client,
            path="/releases",
            params={},
            model_cls=Release,
            items_key="releases",
        )
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
                200,
                json=make_paginated_response(
                    "releases", [make_release()], page=3, pages=5
                ),
            )
        )
        page = SyncPage(
            client=client,
            path="/releases",
            params={"page": 3},
            model_cls=Release,
            items_key="releases",
        )
        next(iter(page))
        assert page.page == 3
        request = respx_mock.calls.last.request
        assert request.url.params["page"] == "3"

    def test_per_page_passed_through(self, client, respx_mock):
        """per_page param is sent to the API."""
        respx_mock.get("/releases").mock(
            return_value=respx.MockResponse(
                200,
                json=make_paginated_response("releases", [make_release()], per_page=10),
            )
        )
        page = SyncPage(
            client=client,
            path="/releases",
            params={"per_page": 10},
            model_cls=Release,
            items_key="releases",
        )
        next(iter(page))
        assert page.per_page == 10
        request = respx_mock.calls.last.request
        assert request.url.params["per_page"] == "10"


class TestErrors:
    def test_error_on_first_page(self, no_retry_client, respx_mock):
        respx_mock.get("/releases").mock(
            return_value=respx.MockResponse(500, json={"message": "Server Error"})
        )
        page = SyncPage(
            client=no_retry_client,
            path="/releases",
            params={},
            model_cls=Release,
            items_key="releases",
        )
        with pytest.raises(DiscogsAPIError):
            list(page)


def _submissions_page(
    page: int, pages: int, *, releases: list[dict], artists: list[dict] | None = None
) -> dict:
    body: dict = {
        "pagination": {
            "page": page,
            "pages": pages,
            "per_page": 50,
            "items": 2,
            "urls": {},
        },
        "submissions": {"releases": releases, "artists": artists or []},
    }
    if page < pages:
        body["pagination"]["urls"]["next"] = (
            f"{BASE_URL}/users/trent_reznor/submissions?page={page + 1}"
        )
    return body


class TestEmptySelectedCategories:
    """An empty selected category must not truncate iteration."""

    def test_continues_past_an_empty_middle_page(self, client, respx_mock):
        pages = [
            _submissions_page(
                1, 3, releases=[make_release(id=1, title="Pretty Hate Machine")]
            ),
            _submissions_page(
                2, 3, releases=[], artists=[{"id": 3857, "name": "Nine Inch Nails"}]
            ),
            _submissions_page(
                3, 3, releases=[make_release(id=2, title="The Downward Spiral")]
            ),
        ]
        responses = iter(pages)
        route = respx_mock.get("/users/trent_reznor/submissions").mock(
            side_effect=lambda req: respx.MockResponse(200, json=next(responses))
        )

        titles = [
            item.title for item in client.users.get("trent_reznor").submissions.list()
        ]

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

        titles = [
            item.title for item in client.users.get("trent_reznor").submissions.list()
        ]

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
        respx_mock.get("/users/trent_reznor/submissions").mock(
            side_effect=lambda req: next(responses)
        )

        with pytest.raises(DiscogsAPIError) as exc_info:
            _ = list(no_retry_client.users.get("trent_reznor").submissions.list())

        # Truncation would have looked like success.
        assert exc_info.value.status_code == 502


PROXY = "https://proxy.example"


@pytest.fixture
def upstream():
    """Catch-all mock on every origin, recording each request's URL and credentials.

    Append the bodies to serve, in order, to the returned list.
    """
    sent: list[tuple[str, str | None]] = []
    bodies: list[dict] = []

    def respond(request):
        sent.append((str(request.url), request.headers.get("Authorization")))
        return respx.MockResponse(200, json=bodies.pop(0))

    with respx.mock(using="httpcore2") as router:
        router.route().mock(side_effect=respond)
        yield sent, bodies


def _two_pages(next_url: str) -> list[dict]:
    return [
        make_paginated_response(
            "releases",
            [make_release(id=1, title="Pretty Hate Machine")],
            page=1,
            pages=2,
            per_page=1,
            next_url=next_url,
        ),
        make_paginated_response(
            "releases",
            [make_release(id=2, title="Broken")],
            page=2,
            pages=2,
            per_page=1,
        ),
    ]


def _releases(client: Discogs) -> SyncPage[Release]:
    return SyncPage(
        client=client,
        path="/releases",
        params={"per_page": 1},
        model_cls=Release,
        items_key="releases",
    )


class TestNextLinkOrigin:
    """``pagination.urls.next`` comes from the body, so it must not steer requests."""

    def test_default_base_url_follows_discogs_link(self, upstream):
        sent, bodies = upstream
        next_url = f"{BASE_URL}/releases?page=2&per_page=1"
        bodies.extend(_two_pages(next_url))
        client = Discogs(token="test-token")

        titles = [item.title for item in _releases(client)]

        assert titles == ["Pretty Hate Machine", "Broken"]
        assert sent[1] == (next_url, "Discogs token=test-token")

    def test_discogs_link_is_rebased_onto_proxy(self, upstream):
        sent, bodies = upstream
        bodies.extend(_two_pages(f"{BASE_URL}/releases?page=2&per_page=1"))
        client = Discogs(token="test-token", base_url=PROXY)

        titles = [item.title for item in _releases(client)]

        assert titles == ["Pretty Hate Machine", "Broken"]
        assert [url for url, _ in sent] == [
            f"{PROXY}/releases?page=1&per_page=1",
            f"{PROXY}/releases?page=2&per_page=1",
        ]

    @pytest.mark.parametrize(
        ("next_url", "expected"),
        [
            (f"{BASE_URL}/releases?page=2", "/releases?page=2"),
            (f"{PROXY}/discogs/releases?page=2", "/releases?page=2"),
            # Host case and an explicit default port do not change the origin.
            ("https://PROXY.Example:443/discogs/releases?page=2", "/releases?page=2"),
            ("https://API.discogs.com:443/releases?page=2", "/releases?page=2"),
            # Only the configured origin carries the base path, at a segment edge.
            (f"{BASE_URL}/discogs/releases?page=2", "/discogs/releases?page=2"),
            (f"{PROXY}/discogsx/releases?page=2", "/discogsx/releases?page=2"),
            # Dot segments resolve before the base path is added, never above it.
            (f"{BASE_URL}/../steal", "/steal"),
            (f"{PROXY}/discogs/../steal", "/steal"),
            (f"{BASE_URL}/./releases?page=2", "/releases?page=2"),
            # The query string is passed through untouched.
            (
                f"{BASE_URL}/releases?q=a%2Bb&empty=&page=2",
                "/releases?q=a%2Bb&empty=&page=2",
            ),
        ],
    )
    def test_link_is_rebased_under_base_path(self, upstream, next_url, expected):
        sent, bodies = upstream
        bodies.extend(_two_pages(next_url))
        client = Discogs(token="test-token", base_url=f"{PROXY}/discogs/")

        _ = list(_releases(client))

        assert sent[1][0] == f"{PROXY}/discogs{expected}"

    @pytest.mark.parametrize(
        ("base_url", "next_url", "message_end"),
        [
            (BASE_URL, "https://evil.example/steal", "origin https://evil.example"),
            (BASE_URL, "https://user:pw@evil.example/s", "origin https://evil.example"),
            (BASE_URL, "http://api.discogs.com/s", "origin http://api.discogs.com"),
            (
                BASE_URL,
                "https://api.discogs.com:8443/s",
                "origin https://api.discogs.com:8443",
            ),
            (PROXY, "https://evil.example/steal", "origin https://evil.example"),
            (PROXY, "http://proxy.example/s", "origin http://proxy.example"),
            (
                PROXY,
                "https://proxy.example:8443/s",
                "origin https://proxy.example:8443",
            ),
            (BASE_URL, "/releases?page=2", "link without an origin"),
            (BASE_URL, "https://api.discogs.com:99999/s", "malformed pagination link"),
            (BASE_URL, "https://[::1/releases?page=2", "malformed pagination link"),
        ],
    )
    def test_rejected_link_raises_after_current_page(
        self, upstream, base_url, next_url, message_end
    ):
        sent, bodies = upstream
        bodies.extend(_two_pages(next_url))
        client = Discogs(token="test-token", base_url=base_url)
        page = _releases(client)
        titles = []

        with pytest.raises(DiscogsError, match=f"{re.escape(message_end)}$"):
            for item in page:
                titles.append(item.title)

        assert titles == ["Pretty Hate Machine"]
        assert len(sent) == 1
        assert page.next_url == next_url

    def test_cache_key_uses_configured_origin(self, upstream):
        sent, bodies = upstream
        bodies.extend(_two_pages(f"{BASE_URL}/releases?page=2&per_page=1"))
        client = Discogs(token="test-token", base_url=PROXY, cache=True)
        _ = list(_releases(client))

        # Served only if page 2 was stored under the proxy URL, not the link's.
        with client.cache_only():
            response = client._send("GET", f"{PROXY}/releases?page=2&per_page=1")
        client.close()

        assert response.json()["releases"][0]["title"] == "Broken"
        assert len(sent) == 2
