"""Tests for async Uploads resource."""

from __future__ import annotations

import pytest
import respx

from discogs_sdk._exceptions import DiscogsAPIError
from discogs_sdk.models.upload import Upload
from tests.conftest import make_paginated_response, make_upload, make_upload_completed


class TestUploadsCreate:
    async def test_create(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/add").mock(
            return_value=respx.MockResponse(200)
        )
        await client.uploads.create(file=str(csv_file))

    async def test_create_error(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/add").mock(
            return_value=respx.MockResponse(400, json={"message": "Bad"})
        )
        with pytest.raises(DiscogsAPIError):
            await client.uploads.create(file=str(csv_file))


class TestUploadsChange:
    async def test_change(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/change").mock(
            return_value=respx.MockResponse(200)
        )
        await client.uploads.change(file=str(csv_file))

    async def test_change_error(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/change").mock(
            return_value=respx.MockResponse(400, json={"message": "Bad"})
        )
        with pytest.raises(DiscogsAPIError):
            await client.uploads.change(file=str(csv_file))


class TestUploadsDelete:
    async def test_delete(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/delete").mock(
            return_value=respx.MockResponse(200)
        )
        await client.uploads.delete(file=str(csv_file))

    async def test_delete_error(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/delete").mock(
            return_value=respx.MockResponse(400, json={"message": "Bad"})
        )
        with pytest.raises(DiscogsAPIError):
            await client.uploads.delete(file=str(csv_file))


class TestUploadsList:
    async def test_list(self, client, respx_mock):
        respx_mock.get("/inventory/upload").mock(
            return_value=respx.MockResponse(
                200,
                json=make_paginated_response(
                    "items", [make_upload(), make_upload_completed(id=2)]
                ),
            )
        )
        results = [item async for item in client.uploads.list()]
        assert [upload.id for upload in results] == [1, 2]
        assert (
            results[1].results == "CSV file contains 1 records.<p>Processed 1 records."
        )


class TestUploadsGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.uploads.get(1)
        assert respx_mock.calls.call_count == 0

    async def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/inventory/upload/1").mock(
            return_value=respx.MockResponse(200, json=make_upload())
        )
        result = await client.uploads.get(1)
        assert isinstance(result, Upload)
        assert result.id == 1

    async def test_completed_upload_returns_its_results_string(
        self, client, respx_mock
    ):
        respx_mock.get("/inventory/upload/1").mock(
            return_value=respx.MockResponse(200, json=make_upload_completed())
        )
        result = await client.uploads.get(1)
        assert result.results == "CSV file contains 1 records.<p>Processed 1 records."

    async def test_pending_upload_has_no_results(self, client, respx_mock):
        respx_mock.get("/inventory/upload/1").mock(
            return_value=respx.MockResponse(200, json=make_upload())
        )
        assert (await client.uploads.get(1)).results is None

    async def test_null_results_stays_none(self, client, respx_mock):
        body = make_upload() | {"results": None}
        respx_mock.get("/inventory/upload/1").mock(
            return_value=respx.MockResponse(200, json=body)
        )
        assert (await client.uploads.get(1)).results is None
