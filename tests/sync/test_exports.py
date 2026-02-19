"""Tests for sync Exports resource."""

from __future__ import annotations

import httpx
import pytest

from discogs_sdk._exceptions import DiscogsAPIError, DiscogsConnectionError
from discogs_sdk.models.export import Export

from tests.conftest import make_export, make_paginated_response


class TestExportsRequest:
    def test_request_success(self, client, respx_mock):
        respx_mock.post("/inventory/export").mock(return_value=httpx.Response(200))
        client.exports.request()

    def test_request_error(self, client, respx_mock):
        respx_mock.post("/inventory/export").mock(return_value=httpx.Response(403, json={"message": "Forbidden"}))
        with pytest.raises(DiscogsAPIError):
            client.exports.request()


class TestExportsList:
    def test_list(self, client, respx_mock):
        respx_mock.get("/inventory/export").mock(
            return_value=httpx.Response(200, json=make_paginated_response("items", [make_export()]))
        )
        results = list(client.exports.list())
        assert len(results) == 1
        assert isinstance(results[0], Export)


class TestExportsGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.exports.get(1)
        assert respx_mock.calls.call_count == 0

    def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/inventory/export/1").mock(return_value=httpx.Response(200, json=make_export()))
        lazy = client.exports.get(1)
        assert lazy.id == 1


class TestExportsDownload:
    def test_download_returns_bytes(self, client, respx_mock):
        respx_mock.get("/inventory/export/1/download").mock(return_value=httpx.Response(200, content=b"csv,data,here"))
        result = client.exports.download(1)
        assert result == b"csv,data,here"

    def test_download_error(self, client, respx_mock):
        respx_mock.get("/inventory/export/999/download").mock(return_value=httpx.Response(404, text="Not Found"))
        with pytest.raises(DiscogsAPIError):
            client.exports.download(999)

    def test_download_connect_error(self, no_retry_client, respx_mock):
        respx_mock.get("/inventory/export/1/download").mock(side_effect=httpx.ConnectError("Connection refused"))
        with pytest.raises(DiscogsConnectionError):
            no_retry_client.exports.download(1)
