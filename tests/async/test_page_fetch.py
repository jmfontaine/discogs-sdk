"""AsyncPage.fetch() sends one request for one page and leaves iteration alone (#168)."""

from __future__ import annotations

import pytest
import respx

from discogs_sdk import AsyncDiscogs, DiscogsError, PageResult
from tests.conftest import BASE_URL, make_artist_release, make_paginated_response

PATH = "/artists/3857/releases"
PAGES = 3
PER_PAGE = 2


def _url(page: int) -> str:
    return f"{BASE_URL}{PATH}?page={page}&per_page={PER_PAGE}"


def _titles(page: int) -> list[str]:
    return [f"Track {page}.{i}" for i in range(PER_PAGE)]


def _three_pages(router) -> respx.Route:
    """Serve a three-page listing, answering by the requested page number."""

    def respond(request):
        page = int(request.url.params.get("page", "1"))
        body = make_paginated_response(
            "releases",
            [
                make_artist_release(id=page * 10 + i, title=title)
                for i, title in enumerate(_titles(page))
            ],
            page=page,
            pages=PAGES,
            per_page=PER_PAGE,
            total_items=PAGES * PER_PAGE,
            next_url=_url(page + 1) if page < PAGES else None,
        )
        return respx.MockResponse(200, json=body)

    return router.get(PATH).mock(side_effect=respond)


def _listing(client: AsyncDiscogs, page: int | None = None):
    return client.artists.get(3857).releases.list(page=page, per_page=PER_PAGE)


ALL_TITLES = [t for page in range(1, PAGES + 1) for t in _titles(page)]


class TestFetch:
    async def test_fetches_exactly_the_requested_page(self, client, respx_mock):
        route = _three_pages(respx_mock)
        result = await _listing(client, page=2).fetch()
        assert route.call_count == 1
        request = route.calls.last.request
        assert request.url.params["page"] == "2"
        assert request.url.params["per_page"] == str(PER_PAGE)
        assert isinstance(result, PageResult)
        assert [r.title for r in result.items] == _titles(2)
        assert (result.page, result.per_page) == (2, PER_PAGE)
        assert (result.total_items, result.total_pages) == (PAGES * PER_PAGE, PAGES)
        assert result.urls == {"next": _url(3)}
        _ = result.items, result.urls
        assert route.call_count == 1

    async def test_second_fetch_is_a_cache_hit(self, respx_mock):
        route = _three_pages(respx_mock)
        client = AsyncDiscogs(token="t", cache=True)
        listing = _listing(client, page=2)
        first = await listing.fetch()
        second = await listing.fetch()
        await client.close()
        assert first == second
        assert route.call_count == 1

    async def test_second_fetch_under_no_cache_is_a_second_request(self, respx_mock):
        route = _three_pages(respx_mock)
        client = AsyncDiscogs(token="t", cache=True)
        listing = _listing(client, page=2)
        async with client.no_cache():
            first = await listing.fetch()
            second = await listing.fetch()
        await client.close()
        assert first == second
        assert route.call_count == 2

    async def test_fetch_then_iteration_yields_the_whole_listing(
        self, client, respx_mock
    ):
        _three_pages(respx_mock)
        listing = _listing(client)
        await listing.fetch()
        assert listing.page is None
        assert [r.title async for r in listing] == ALL_TITLES

    async def test_fetch_mid_iteration_neither_repeats_nor_skips(
        self, client, respx_mock
    ):
        _three_pages(respx_mock)
        listing = _listing(client)
        seen = [(await anext(listing)).title for _ in range(3)]
        assert listing.page == 2
        result = await listing.fetch()
        assert result.page == 1
        assert listing.page == 2
        assert listing.next_url == _url(3)
        seen += [r.title async for r in listing]
        assert seen == ALL_TITLES

    async def test_fetch_after_iteration_leaves_it_exhausted(self, client, respx_mock):
        _three_pages(respx_mock)
        listing = _listing(client)
        assert [r.title async for r in listing] == ALL_TITLES
        assert [r.title for r in (await listing.fetch()).items] == _titles(1)
        assert [r.title async for r in listing] == []
        assert listing.page == PAGES

    @pytest.mark.parametrize(
        "body",
        [
            {"releases": {}, "pagination": {"page": 1}},
            {"releases": [], "pagination": []},
        ],
        ids=["items-object", "pagination-list"],
    )
    async def test_malformed_envelope_raises_like_iteration(
        self, client, respx_mock, body
    ):
        respx_mock.get(PATH).respond(200, json=body)
        with pytest.raises(DiscogsError) as fetched:
            await _listing(client).fetch()
        with pytest.raises(DiscogsError) as iterated:
            await anext(_listing(client))
        assert type(fetched.value) is type(iterated.value)
        assert str(fetched.value) == str(iterated.value)
