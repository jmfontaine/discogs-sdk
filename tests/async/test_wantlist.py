"""Tests for async Wantlist resource."""

from __future__ import annotations

import httpx
import pytest

from discogs_sdk._exceptions import NotFoundError
from discogs_sdk.models.wantlist import Want

from tests.conftest import make_paginated_response, make_want


class TestWantlistList:
    async def test_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/wants").mock(
            return_value=httpx.Response(200, json=make_paginated_response("wants", [make_want()]))
        )
        lazy = client.users.get("trent_reznor")
        results = [item async for item in lazy.wantlist.list()]
        assert len(results) == 1
        assert isinstance(results[0], Want)
        assert results[0].id == 400027


class TestWantlistCreate:
    async def test_create_uses_put(self, client, respx_mock):
        """Wantlist create uses PUT, not POST — critical edge case."""
        respx_mock.put("/users/trent_reznor/wants/400027").mock(return_value=httpx.Response(201, json=make_want()))
        lazy = client.users.get("trent_reznor")
        result = await lazy.wantlist.create(release_id=400027)
        assert isinstance(result, Want)
        # Verify PUT was used
        assert respx_mock.calls[0].request.method == "PUT"

    async def test_create_with_notes_and_rating(self, client, respx_mock):
        respx_mock.put("/users/trent_reznor/wants/400027").mock(
            return_value=httpx.Response(201, json=make_want(notes="Masterpiece", rating=5))
        )
        lazy = client.users.get("trent_reznor")
        result = await lazy.wantlist.create(release_id=400027, notes="Masterpiece", rating=5)
        assert result.notes == "Masterpiece"
        assert result.rating == 5

    async def test_create_without_optional_fields(self, client, respx_mock):
        respx_mock.put("/users/trent_reznor/wants/400027").mock(return_value=httpx.Response(201, json=make_want()))
        lazy = client.users.get("trent_reznor")
        await lazy.wantlist.create(release_id=400027)
        body = respx_mock.calls[0].request.content
        # Empty body when no notes/rating
        assert b"notes" not in body
        assert b"rating" not in body


class TestWantlistUpdate:
    async def test_update_uses_post(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor/wants/400027").mock(
            return_value=httpx.Response(200, json=make_want(rating=3))
        )
        lazy = client.users.get("trent_reznor")
        result = await lazy.wantlist.update(400027, rating=3)
        assert isinstance(result, Want)
        assert respx_mock.calls[0].request.method == "POST"


class TestWantlistDelete:
    async def test_delete(self, client, respx_mock):
        respx_mock.delete("/users/trent_reznor/wants/400027").mock(return_value=httpx.Response(204))
        lazy = client.users.get("trent_reznor")
        await lazy.wantlist.delete(400027)

    async def test_delete_empty_body_error(self, client, respx_mock):
        respx_mock.delete("/users/trent_reznor/wants/999").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        lazy = client.users.get("trent_reznor")
        with pytest.raises(NotFoundError):
            await lazy.wantlist.delete(999)


class TestWantModel:
    async def test_required_fields(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/wants").mock(
            return_value=httpx.Response(200, json=make_paginated_response("wants", [{"id": 1}]))
        )
        lazy = client.users.get("trent_reznor")
        results = [item async for item in lazy.wantlist.list()]
        assert results[0].notes is None
        assert results[0].rating is None

    async def test_extra_allow(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/wants").mock(
            return_value=httpx.Response(
                200,
                json=make_paginated_response("wants", [{"id": 1, "_unknown_extra_field": "test"}]),
            )
        )
        lazy = client.users.get("trent_reznor")
        results = [item async for item in lazy.wantlist.list()]
        assert results[0].model_extra["_unknown_extra_field"] == "test"
