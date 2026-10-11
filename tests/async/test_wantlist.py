"""Tests for async Wantlist resource."""

from __future__ import annotations

import json

import pytest
import respx

from discogs_sdk._exceptions import NotFoundError
from discogs_sdk.models.wantlist import Want
from tests.conftest import make_paginated_response, make_want


class TestWantlistList:
    async def test_list(self, client, respx_mock):
        route = respx_mock.get("/users/trent_reznor/wants").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("wants", [make_want()])
            )
        )
        lazy = client.users.get("trent_reznor")
        results = [item async for item in lazy.wantlist.list(page=2, per_page=50)]
        assert len(results) == 1
        assert isinstance(results[0], Want)
        assert results[0].id == 400027
        params = route.calls.last.request.url.params
        assert params["page"] == "2"
        assert params["per_page"] == "50"


class TestWantlistCreate:
    async def test_create_uses_put_with_no_body(self, client, respx_mock):
        """Wantlist create uses PUT, not POST — critical edge case.

        The endpoint takes nothing but the release id: Discogs discards `notes`
        and `rating` sent here, so the SDK does not offer them.
        """
        route = respx_mock.put("/users/trent_reznor/wants/400027").mock(
            return_value=respx.MockResponse(201, json=make_want())
        )
        lazy = client.users.get("trent_reznor")
        result = await lazy.wantlist.create(release_id=400027)
        assert isinstance(result, Want)
        request = route.calls.last.request
        assert request.method == "PUT"
        assert request.content == b""
        assert not request.url.params


class TestWantlistUpdate:
    async def test_update_uses_post(self, client, respx_mock):
        route = respx_mock.post("/users/trent_reznor/wants/400027").mock(
            return_value=respx.MockResponse(200, json=make_want(rating=3))
        )
        lazy = client.users.get("trent_reznor")
        result = await lazy.wantlist.update(400027, rating=3)
        assert isinstance(result, Want)
        request = route.calls.last.request
        assert request.method == "POST"
        assert json.loads(request.content) == {"rating": 3}
        assert not request.url.params

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
    async def test_update_sends_only_given_fields(
        self, client, respx_mock, fields, body
    ):
        route = respx_mock.post("/users/trent_reznor/wants/400027").mock(
            return_value=respx.MockResponse(200, json=make_want())
        )
        await client.users.get("trent_reznor").wantlist.update(400027, **fields)
        assert json.loads(route.calls[0].request.content) == body

    async def test_update_rejects_a_misspelled_field(self, client, respx_mock):
        wantlist = client.users.get("trent_reznor").wantlist
        with pytest.raises(TypeError):
            await wantlist.update(400027, note="Original pressing")  # ty: ignore[unknown-argument]
        assert respx_mock.calls.call_count == 0


class TestWantlistDelete:
    async def test_delete(self, client, respx_mock):
        respx_mock.delete("/users/trent_reznor/wants/400027").mock(
            return_value=respx.MockResponse(204)
        )
        lazy = client.users.get("trent_reznor")
        await lazy.wantlist.delete(400027)

    async def test_delete_error(self, client, respx_mock):
        respx_mock.delete("/users/trent_reznor/wants/999").mock(
            return_value=respx.MockResponse(404, json={"message": "Not Found"})
        )
        lazy = client.users.get("trent_reznor")
        with pytest.raises(NotFoundError):
            await lazy.wantlist.delete(999)


class TestWantModel:
    async def test_required_fields(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/wants").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("wants", [{"id": 1}])
            )
        )
        lazy = client.users.get("trent_reznor")
        results = [item async for item in lazy.wantlist.list()]
        assert results[0].notes is None
        assert results[0].rating is None

    async def test_extra_allow(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/wants").mock(
            return_value=respx.MockResponse(
                200,
                json=make_paginated_response(
                    "wants", [{"id": 1, "_unknown_extra_field": "test"}]
                ),
            )
        )
        lazy = client.users.get("trent_reznor")
        results = [item async for item in lazy.wantlist.list()]
        assert results[0].model_extra["_unknown_extra_field"] == "test"


class TestUsernamePathEncoding:
    async def test_list_encodes_username_once(self, client, respx_mock):
        route = respx_mock.route().respond(
            200, json=make_paginated_response("wants", [])
        )
        _ = [item async for item in client.users.get("a/b?c#d").wantlist.list()]
        path = route.calls.last.request.url.raw_path.partition(b"?")[0]
        assert path == b"/users/a%2Fb%3Fc%23d/wants"

    async def test_delete_encodes_username_once(self, client, respx_mock):
        route = respx_mock.route().respond(204)
        await client.users.get("a/b?c#d").wantlist.delete(352665)
        path = route.calls.last.request.url.raw_path
        assert path == b"/users/a%2Fb%3Fc%23d/wants/352665"
