"""Behavioural regressions for the sequences the examples demonstrate.

tests/test_examples.py only parses and resolves imports. These exercise the
lifecycles and orderings that were previously wrong in examples/, under mocked
HTTP, so a regression fails here instead of in a user's terminal.
"""

from __future__ import annotations

import pytest
import respx

from discogs_sdk import AsyncDiscogs
from tests.conftest import BASE_URL, make_artist, make_artist_release, make_paginated_response


@pytest.fixture
def respx_mock():
    with respx.mock(base_url=BASE_URL) as router:
        yield router


class TestAsyncProxyVersusModel:
    """examples/async_usage.py: sub-resources live on the proxy, not the model."""

    async def test_proxy_survives_resolution_and_still_lists_releases(self, respx_mock):
        respx_mock.get("/artists/3857").respond(200, json=make_artist(id=3857))
        respx_mock.get("/artists/3857/releases").respond(
            200, json=make_paginated_response("releases", [make_artist_release(title="The Downward Spiral")])
        )

        async with AsyncDiscogs(token="t") as client:
            artist_proxy = client.artists.get(3857)
            artist = await artist_proxy
            assert artist.name == "Nine Inch Nails"

            titles = [release.title async for release in artist_proxy.releases.list(sort="year")]

        assert titles == ["The Downward Spiral"]

    async def test_resolved_model_has_no_sub_resources(self, respx_mock):
        respx_mock.get("/artists/3857").respond(200, json=make_artist(id=3857))

        async with AsyncDiscogs(token="t") as client:
            artist = await client.artists.get(3857)
            with pytest.raises(AttributeError):
                artist.releases  # noqa: B018
