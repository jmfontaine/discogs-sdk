"""Tests for sync Wantlist resource."""

from __future__ import annotations

import json

import pytest
import respx

from discogs_sdk._exceptions import NotFoundError
from discogs_sdk.models.wantlist import Want
from tests.conftest import make_paginated_response, make_want


class TestWantlistList:
    def test_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/wants").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("wants", [make_want()])
            )
        )
        lazy = client.users.get("trent_reznor")
        results = list(lazy.wantlist.list())
        assert len(results) == 1
        assert isinstance(results[0], Want)


class TestWantlistCreate:
    def test_create_uses_put_with_no_body(self, client, respx_mock):
        """Wantlist create uses PUT, not POST — critical edge case.

        The endpoint takes nothing but the release id: Discogs discards `notes`
        and `rating` sent here, so the SDK does not offer them.
        """
        respx_mock.put("/users/trent_reznor/wants/400027").mock(
            return_value=respx.MockResponse(201, json=make_want())
        )
        lazy = client.users.get("trent_reznor")
        result = lazy.wantlist.create(release_id=400027)
        assert isinstance(result, Want)
        assert respx_mock.calls[0].request.method == "PUT"
        assert not respx_mock.calls[0].request.content


class TestWantlistUpdate:
    def test_update_uses_post(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor/wants/400027").mock(
            return_value=respx.MockResponse(200, json=make_want(rating=3))
        )
        lazy = client.users.get("trent_reznor")
        result = lazy.wantlist.update(400027, rating=3)
        assert isinstance(result, Want)
        assert respx_mock.calls[0].request.method == "POST"

    @pytest.mark.parametrize(
        ("fields", "body"),
        [
            (
                {"notes": "Original pressing", "rating": 4},
                {"notes": "Original pressing", "rating": 4},
            ),
            ({"notes": "Original pressing"}, {"notes": "Original pressing"}),
            # A falsy value is still a value: only None is left out.
            ({"notes": "", "rating": 0}, {"notes": "", "rating": 0}),
        ],
    )
    def test_update_sends_only_given_fields(self, client, respx_mock, fields, body):
        route = respx_mock.post("/users/trent_reznor/wants/400027").mock(
            return_value=respx.MockResponse(200, json=make_want())
        )
        client.users.get("trent_reznor").wantlist.update(400027, **fields)
        assert json.loads(route.calls[0].request.content) == body

    def test_update_rejects_a_misspelled_field(self, client, respx_mock):
        wantlist = client.users.get("trent_reznor").wantlist
        with pytest.raises(TypeError):
            wantlist.update(400027, note="Original pressing")  # ty: ignore[unknown-argument]
        assert respx_mock.calls.call_count == 0


class TestWantlistDelete:
    def test_delete(self, client, respx_mock):
        respx_mock.delete("/users/trent_reznor/wants/400027").mock(
            return_value=respx.MockResponse(204)
        )
        lazy = client.users.get("trent_reznor")
        lazy.wantlist.delete(400027)

    def test_delete_error(self, client, respx_mock):
        respx_mock.delete("/users/trent_reznor/wants/999").mock(
            return_value=respx.MockResponse(404, json={"message": "Not Found"})
        )
        lazy = client.users.get("trent_reznor")
        with pytest.raises(NotFoundError):
            lazy.wantlist.delete(999)


class TestUsernamePathEncoding:
    def test_list_encodes_username_once(self, client, respx_mock):
        route = respx_mock.route().respond(
            200, json=make_paginated_response("wants", [])
        )
        _ = list(client.users.get("a/b?c#d").wantlist.list())
        path = route.calls.last.request.url.raw_path.partition(b"?")[0]
        assert path == b"/users/a%2Fb%3Fc%23d/wants"

    def test_delete_encodes_username_once(self, client, respx_mock):
        route = respx_mock.route().respond(204)
        client.users.get("a/b?c#d").wantlist.delete(352665)
        path = route.calls.last.request.url.raw_path
        assert path == b"/users/a%2Fb%3Fc%23d/wants/352665"
