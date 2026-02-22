"""Tests for async Artists resource."""

from __future__ import annotations

import httpx

from discogs_sdk.models.artist import Artist, ArtistRelease

from tests.conftest import (
    make_artist,
    make_artist_release,
    make_paginated_response,
)


class TestArtistsGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.artists.get(40)
        assert respx_mock.calls.call_count == 0

    async def test_get_resolves_to_artist(self, client, respx_mock):
        respx_mock.get("/artists/40").mock(return_value=httpx.Response(200, json=make_artist()))
        result = await client.artists.get(40)
        assert isinstance(result, Artist)
        assert result.name == "Nine Inch Nails"


class TestArtistReleases:
    def test_releases_accessible_without_http(self, client, respx_mock):
        lazy = client.artists.get(40)
        _ = lazy.releases
        assert respx_mock.calls.call_count == 0

    async def test_releases_list(self, client, respx_mock):
        items = [make_artist_release(id=i, title=f"R{i}") for i in range(2)]
        respx_mock.get("/artists/40/releases").mock(
            return_value=httpx.Response(200, json=make_paginated_response("releases", items))
        )
        lazy = client.artists.get(40)
        results = [item async for item in lazy.releases.list()]
        assert len(results) == 2
        assert all(isinstance(r, ArtistRelease) for r in results)

    async def test_releases_list_with_page_and_per_page(self, client, respx_mock):
        respx_mock.get("/artists/40/releases").mock(
            return_value=httpx.Response(
                200, json=make_paginated_response("releases", [make_artist_release()], page=2, per_page=25)
            )
        )
        lazy = client.artists.get(40)
        page = lazy.releases.list(page=2, per_page=25)
        results = [item async for item in page]
        assert len(results) == 1
        assert page.page == 2
        assert page.per_page == 25
        request = respx_mock.calls.last.request
        assert request.url.params["page"] == "2"
        assert request.url.params["per_page"] == "25"

    async def test_releases_list_with_sort(self, client, respx_mock):
        respx_mock.get("/artists/40/releases").mock(
            return_value=httpx.Response(200, json=make_paginated_response("releases", [make_artist_release()]))
        )
        lazy = client.artists.get(40)
        results = [item async for item in lazy.releases.list(sort="year", sort_order="desc")]
        assert len(results) == 1


class TestArtistModel:
    async def test_required_fields(self, client, respx_mock):
        respx_mock.get("/artists/1").mock(return_value=httpx.Response(200, json={"id": 1, "name": "A"}))
        result = await client.artists.get(1)
        assert result.id == 1
        assert result.profile is None

    async def test_extra_allow(self, client, respx_mock):
        respx_mock.get("/artists/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "name": "A", "realname": "Trent Reznor"})
        )
        result = await client.artists.get(1)
        assert result.model_extra["realname"] == "Trent Reznor"
