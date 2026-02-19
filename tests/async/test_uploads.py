"""Tests for async Uploads resource."""

from __future__ import annotations

import httpx
import pytest

from discogs_sdk._exceptions import DiscogsAPIError
from discogs_sdk.models.upload import Upload

from tests.conftest import make_paginated_response, make_upload


class TestUploadsCreate:
    async def test_create(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/add").mock(return_value=httpx.Response(200))
        await client.uploads.create(file=str(csv_file))

    async def test_create_error(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/add").mock(return_value=httpx.Response(400, json={"message": "Bad"}))
        with pytest.raises(DiscogsAPIError):
            await client.uploads.create(file=str(csv_file))


class TestUploadsChange:
    async def test_change(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/change").mock(return_value=httpx.Response(200))
        await client.uploads.change(file=str(csv_file))

    async def test_change_error(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/change").mock(return_value=httpx.Response(400, json={"message": "Bad"}))
        with pytest.raises(DiscogsAPIError):
            await client.uploads.change(file=str(csv_file))


class TestUploadsDelete:
    async def test_delete(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/delete").mock(return_value=httpx.Response(200))
        await client.uploads.delete(file=str(csv_file))

    async def test_delete_error(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/delete").mock(return_value=httpx.Response(400, json={"message": "Bad"}))
        with pytest.raises(DiscogsAPIError):
            await client.uploads.delete(file=str(csv_file))


class TestUploadsList:
    async def test_list(self, client, respx_mock):
        respx_mock.get("/inventory/upload").mock(
            return_value=httpx.Response(200, json=make_paginated_response("items", [make_upload()]))
        )
        results = [item async for item in client.uploads.list()]
        assert len(results) == 1
        assert isinstance(results[0], Upload)


class TestUploadsGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.uploads.get(1)
        assert respx_mock.calls.call_count == 0

    async def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/inventory/upload/1").mock(return_value=httpx.Response(200, json=make_upload()))
        result = await client.uploads.get(1)
        assert isinstance(result, Upload)
        assert result.id == 1
