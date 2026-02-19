"""Tests for async Exports resource."""

from __future__ import annotations

import httpx
import pytest

from discogs_sdk._exceptions import DiscogsAPIError, DiscogsConnectionError, ForbiddenError
from discogs_sdk.models.export import Export

from tests.conftest import make_export, make_paginated_response


class TestExportsRequest:
    async def test_request_success(self, client, respx_mock):
        respx_mock.post("/inventory/export").mock(return_value=httpx.Response(200))
        await client.exports.request()

    async def test_request_error_empty_body(self, client, respx_mock):
        respx_mock.post("/inventory/export").mock(return_value=httpx.Response(403, json={"message": "Forbidden"}))
        with pytest.raises(ForbiddenError):
            await client.exports.request()


class TestExportsList:
    async def test_list(self, client, respx_mock):
        respx_mock.get("/inventory/export").mock(
            return_value=httpx.Response(200, json=make_paginated_response("items", [make_export()]))
        )
        results = [item async for item in client.exports.list()]
        assert len(results) == 1
        assert isinstance(results[0], Export)


class TestExportsGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.exports.get(1)
        assert respx_mock.calls.call_count == 0

    async def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/inventory/export/1").mock(return_value=httpx.Response(200, json=make_export()))
        result = await client.exports.get(1)
        assert isinstance(result, Export)
        assert result.id == 1


class TestExportsDownload:
    async def test_download_returns_bytes(self, client, respx_mock):
        respx_mock.get("/inventory/export/1/download").mock(return_value=httpx.Response(200, content=b"csv,data,here"))
        result = await client.exports.download(1)
        assert result == b"csv,data,here"

    async def test_download_error_uses_text(self, client, respx_mock):
        respx_mock.get("/inventory/export/999/download").mock(return_value=httpx.Response(404, text="Not Found"))
        with pytest.raises(DiscogsAPIError):
            await client.exports.download(999)

    async def test_download_connect_error(self, no_retry_client, respx_mock):
        respx_mock.get("/inventory/export/1/download").mock(side_effect=httpx.ConnectError("Connection refused"))
        with pytest.raises(DiscogsConnectionError):
            await no_retry_client.exports.download(1)


class TestExportModel:
    async def test_required_fields(self, client, respx_mock):
        respx_mock.get("/inventory/export/1").mock(return_value=httpx.Response(200, json={"id": 1}))
        result = await client.exports.get(1)
        assert result.status is None

    async def test_extra_allow(self, client, respx_mock):
        respx_mock.get("/inventory/export/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "_unknown_extra_field": "test"})
        )
        result = await client.exports.get(1)
        assert result.model_extra["_unknown_extra_field"] == "test"
