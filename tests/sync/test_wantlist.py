"""Tests for sync Wantlist resource."""

from __future__ import annotations

import httpx
import pytest

from discogs_sdk._exceptions import NotFoundError
from discogs_sdk.models.wantlist import Want

from tests.conftest import make_paginated_response, make_want


class TestWantlistList:
    def test_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/wants").mock(
            return_value=httpx.Response(200, json=make_paginated_response("wants", [make_want()]))
        )
        lazy = client.users.get("trent_reznor")
        results = list(lazy.wantlist.list())
        assert len(results) == 1
        assert isinstance(results[0], Want)


class TestWantlistCreate:
    def test_create_uses_put(self, client, respx_mock):
        """Wantlist create uses PUT, not POST — critical edge case."""
        respx_mock.put("/users/trent_reznor/wants/400027").mock(return_value=httpx.Response(201, json=make_want()))
        lazy = client.users.get("trent_reznor")
        result = lazy.wantlist.create(release_id=400027)
        assert isinstance(result, Want)
        assert respx_mock.calls[0].request.method == "PUT"

    def test_create_with_notes_and_rating(self, client, respx_mock):
        respx_mock.put("/users/trent_reznor/wants/400027").mock(
            return_value=httpx.Response(201, json=make_want(notes="Masterpiece", rating=5))
        )
        lazy = client.users.get("trent_reznor")
        result = lazy.wantlist.create(release_id=400027, notes="Masterpiece", rating=5)
        assert result.notes == "Masterpiece"
        assert result.rating == 5

    def test_create_without_optional_fields(self, client, respx_mock):
        respx_mock.put("/users/trent_reznor/wants/400027").mock(return_value=httpx.Response(201, json=make_want()))
        lazy = client.users.get("trent_reznor")
        lazy.wantlist.create(release_id=400027)
        body = respx_mock.calls[0].request.content
        assert b"notes" not in body
        assert b"rating" not in body


class TestWantlistUpdate:
    def test_update_uses_post(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor/wants/400027").mock(
            return_value=httpx.Response(200, json=make_want(rating=3))
        )
        lazy = client.users.get("trent_reznor")
        result = lazy.wantlist.update(400027, rating=3)
        assert isinstance(result, Want)
        assert respx_mock.calls[0].request.method == "POST"


class TestWantlistDelete:
    def test_delete(self, client, respx_mock):
        respx_mock.delete("/users/trent_reznor/wants/400027").mock(return_value=httpx.Response(204))
        lazy = client.users.get("trent_reznor")
        lazy.wantlist.delete(400027)

    def test_delete_error(self, client, respx_mock):
        respx_mock.delete("/users/trent_reznor/wants/999").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        lazy = client.users.get("trent_reznor")
        with pytest.raises(NotFoundError):
            lazy.wantlist.delete(999)
