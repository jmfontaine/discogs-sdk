"""Tests for sync Artists resource."""

from __future__ import annotations

import httpx

from discogs_sdk.models.artist import ArtistRelease

from tests.conftest import make_artist, make_artist_release, make_paginated_response


class TestArtistsGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.artists.get(40)
        assert respx_mock.calls.call_count == 0

    def test_get_resolves_to_artist(self, client, respx_mock):
        respx_mock.get("/artists/40").mock(return_value=httpx.Response(200, json=make_artist()))
        lazy = client.artists.get(40)
        assert lazy.name == "Nine Inch Nails"


class TestArtistReleases:
    def test_releases_accessible_without_http(self, client, respx_mock):
        lazy = client.artists.get(40)
        _ = lazy.releases
        assert respx_mock.calls.call_count == 0

    def test_releases_list(self, client, respx_mock):
        items = [make_artist_release(id=i, title=f"R{i}") for i in range(2)]
        respx_mock.get("/artists/40/releases").mock(
            return_value=httpx.Response(200, json=make_paginated_response("releases", items))
        )
        lazy = client.artists.get(40)
        results = list(lazy.releases.list())
        assert len(results) == 2
        assert all(isinstance(r, ArtistRelease) for r in results)

    def test_releases_list_with_page_and_per_page(self, client, respx_mock):
        respx_mock.get("/artists/40/releases").mock(
            return_value=httpx.Response(
                200, json=make_paginated_response("releases", [make_artist_release()], page=2, per_page=25)
            )
        )
        lazy = client.artists.get(40)
        page = lazy.releases.list(page=2, per_page=25)
        results = list(page)
        assert len(results) == 1
        assert page.page == 2
        assert page.per_page == 25
        request = respx_mock.calls.last.request
        assert request.url.params["page"] == "2"
        assert request.url.params["per_page"] == "25"

    def test_releases_list_with_sort(self, client, respx_mock):
        respx_mock.get("/artists/40/releases").mock(
            return_value=httpx.Response(200, json=make_paginated_response("releases", [make_artist_release()]))
        )
        lazy = client.artists.get(40)
        results = list(lazy.releases.list(sort="year", sort_order="desc"))
        assert len(results) == 1
