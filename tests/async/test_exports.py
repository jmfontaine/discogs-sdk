"""Tests for async Exports resource."""

from __future__ import annotations

import httpx2
import pytest
import respx

from discogs_sdk import AsyncDiscogs
from discogs_sdk._exceptions import (
    CacheMissError,
    DiscogsAPIError,
    DiscogsConnectionError,
    ForbiddenError,
)
from discogs_sdk.models.export import Export
from tests.conftest import (
    StoreRecordingCache,
    make_export,
    make_paginated_response,
    make_release,
)


class TestExportsRequest:
    async def test_request_success(self, client, respx_mock):
        respx_mock.post("/inventory/export").mock(return_value=respx.MockResponse(200))
        await client.exports.request()

    async def test_request_error_empty_body(self, client, respx_mock):
        respx_mock.post("/inventory/export").mock(
            return_value=respx.MockResponse(403, json={"message": "Forbidden"})
        )
        with pytest.raises(ForbiddenError):
            await client.exports.request()


class TestExportsList:
    async def test_list(self, client, respx_mock):
        respx_mock.get("/inventory/export").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("items", [make_export()])
            )
        )
        results = [item async for item in client.exports.list()]
        assert len(results) == 1
        assert isinstance(results[0], Export)


class TestExportsGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.exports.get(1)
        assert respx_mock.calls.call_count == 0

    async def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/inventory/export/1").mock(
            return_value=respx.MockResponse(200, json=make_export())
        )
        result = await client.exports.get(1)
        assert isinstance(result, Export)
        assert result.id == 1


class TestExportStatusPolling:
    """A status poll has to see the job finish, so it never touches the cache."""

    async def test_each_get_reaches_the_api(self, respx_mock):
        route = respx_mock.get("/inventory/export/1").mock(
            side_effect=[
                respx.MockResponse(200, json=make_export(status="pending")),
                respx.MockResponse(200, json=make_export(status="completed")),
            ]
        )
        client = AsyncDiscogs(token="test-token", cache=True)
        assert (await client.exports.get(1)).status == "pending"
        assert (await client.exports.get(1)).status == "completed"
        assert route.call_count == 2
        await client.close()

    async def test_poll_stores_nothing(self, respx_mock):
        respx_mock.get("/inventory/export/1").respond(200, json=make_export())
        cache = StoreRecordingCache()
        events = []
        client = AsyncDiscogs(token="test-token", cache=cache, on_request=events.append)
        await client.exports.get(1)
        await client.close()
        assert cache.stored_keys == []
        assert [(e.source, e.stored) for e in events] == [("network", False)]

    async def test_other_resources_stay_cached(self, respx_mock):
        respx_mock.get("/inventory/export/1").respond(200, json=make_export())
        route = respx_mock.get("/releases/352665").respond(200, json=make_release())
        client = AsyncDiscogs(token="test-token", cache=True)
        await client.exports.get(1)
        await client.releases.get(352665)
        await client.releases.get(352665)
        assert route.call_count == 1
        await client.close()

    async def test_cache_only_has_nothing_to_serve(self, respx_mock):
        route = respx_mock.get("/inventory/export/1").respond(200, json=make_export())
        client = AsyncDiscogs(token="test-token", cache=True)
        await client.exports.get(1)
        async with client.cache_only():
            with pytest.raises(CacheMissError):
                await client.exports.get(1)
        assert route.call_count == 1
        await client.close()


class TestExportsDownload:
    async def test_download_returns_bytes(self, client, respx_mock):
        respx_mock.get("/inventory/export/1/download").mock(
            return_value=respx.MockResponse(200, content=b"csv,data,here")
        )
        result = await client.exports.download(1)
        assert result == b"csv,data,here"

    async def test_download_error_uses_text(self, client, respx_mock):
        respx_mock.get("/inventory/export/999/download").mock(
            return_value=respx.MockResponse(404, text="Not Found")
        )
        with pytest.raises(DiscogsAPIError):
            await client.exports.download(999)

    async def test_download_connect_error(self, no_retry_client, respx_mock):
        respx_mock.get("/inventory/export/1/download").mock(
            side_effect=httpx2.ConnectError("Connection refused")
        )
        with pytest.raises(DiscogsConnectionError):
            await no_retry_client.exports.download(1)


class TestExportModel:
    async def test_required_fields(self, client, respx_mock):
        respx_mock.get("/inventory/export/1").mock(
            return_value=respx.MockResponse(200, json={"id": 1})
        )
        result = await client.exports.get(1)
        assert result.status is None

    async def test_extra_allow(self, client, respx_mock):
        respx_mock.get("/inventory/export/1").mock(
            return_value=respx.MockResponse(
                200, json={"id": 1, "_unknown_extra_field": "test"}
            )
        )
        result = await client.exports.get(1)
        assert result.model_extra["_unknown_extra_field"] == "test"
