"""Tests for sync Uploads resource."""

from __future__ import annotations

import pytest
import respx

from discogs_sdk import Discogs
from discogs_sdk._exceptions import CacheMissError, DiscogsAPIError
from tests.conftest import (
    StoreRecordingCache,
    make_paginated_response,
    make_release,
    make_upload,
    make_upload_completed,
)


class TestUploadsCreate:
    def test_create(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/add").mock(
            return_value=respx.MockResponse(200)
        )
        client.uploads.create(file=str(csv_file))

    def test_create_error(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/add").mock(
            return_value=respx.MockResponse(400, json={"message": "Bad"})
        )
        with pytest.raises(DiscogsAPIError):
            client.uploads.create(file=str(csv_file))


class TestUploadsChange:
    def test_change(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/change").mock(
            return_value=respx.MockResponse(200)
        )
        client.uploads.change(file=str(csv_file))

    def test_change_error(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/change").mock(
            return_value=respx.MockResponse(400, json={"message": "Bad"})
        )
        with pytest.raises(DiscogsAPIError):
            client.uploads.change(file=str(csv_file))


class TestUploadsDelete:
    def test_delete(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/delete").mock(
            return_value=respx.MockResponse(200)
        )
        client.uploads.delete(file=str(csv_file))

    def test_delete_error(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("header\nrow1")
        respx_mock.post("/inventory/upload/delete").mock(
            return_value=respx.MockResponse(400, json={"message": "Bad"})
        )
        with pytest.raises(DiscogsAPIError):
            client.uploads.delete(file=str(csv_file))


class TestUploadsList:
    def test_list(self, client, respx_mock):
        respx_mock.get("/inventory/upload").mock(
            return_value=respx.MockResponse(
                200,
                json=make_paginated_response(
                    "items", [make_upload(), make_upload_completed(id=2)]
                ),
            )
        )
        results = list(client.uploads.list())
        assert [upload.id for upload in results] == [1, 2]
        assert (
            results[1].results == "CSV file contains 1 records.<p>Processed 1 records."
        )


class TestUploadsGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.uploads.get(1)
        assert respx_mock.calls.call_count == 0

    def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/inventory/upload/1").mock(
            return_value=respx.MockResponse(200, json=make_upload())
        )
        lazy = client.uploads.get(1)
        assert lazy.id == 1

    def test_completed_upload_returns_its_results_string(self, client, respx_mock):
        respx_mock.get("/inventory/upload/1").mock(
            return_value=respx.MockResponse(200, json=make_upload_completed())
        )
        result = client.uploads.get(1)
        assert result.results == "CSV file contains 1 records.<p>Processed 1 records."

    def test_pending_upload_has_no_results(self, client, respx_mock):
        respx_mock.get("/inventory/upload/1").mock(
            return_value=respx.MockResponse(200, json=make_upload())
        )
        assert client.uploads.get(1).results is None

    def test_null_results_stays_none(self, client, respx_mock):
        body = make_upload() | {"results": None}
        respx_mock.get("/inventory/upload/1").mock(
            return_value=respx.MockResponse(200, json=body)
        )
        assert client.uploads.get(1).results is None


class TestUploadStatusPolling:
    """A status poll has to see the job finish, so it never touches the cache."""

    def test_each_get_reaches_the_api(self, respx_mock):
        route = respx_mock.get("/inventory/upload/1").mock(
            side_effect=[
                respx.MockResponse(200, json=make_upload()),
                respx.MockResponse(200, json=make_upload_completed()),
            ]
        )
        client = Discogs(token="test-token", cache=True)
        assert client.uploads.get(1).status == "pending"
        assert client.uploads.get(1).status == "success"
        assert route.call_count == 2
        client.close()

    def test_poll_stores_nothing(self, respx_mock):
        respx_mock.get("/inventory/upload/1").respond(200, json=make_upload())
        cache = StoreRecordingCache()
        events = []
        client = Discogs(token="test-token", cache=cache, on_request=events.append)
        client.uploads.get(1).status  # noqa: B018 — triggers resolve
        client.close()
        assert cache.stored_keys == []
        assert [(e.source, e.stored) for e in events] == [("network", False)]

    def test_other_resources_stay_cached(self, respx_mock):
        respx_mock.get("/inventory/upload/1").respond(200, json=make_upload())
        route = respx_mock.get("/releases/352665").respond(200, json=make_release())
        client = Discogs(token="test-token", cache=True)
        client.uploads.get(1).status  # noqa: B018 — triggers resolve
        client.releases.get(352665).title  # noqa: B018 — triggers resolve
        client.releases.get(352665).title  # noqa: B018 — triggers resolve
        assert route.call_count == 1
        client.close()

    def test_cache_only_has_nothing_to_serve(self, respx_mock):
        route = respx_mock.get("/inventory/upload/1").respond(200, json=make_upload())
        client = Discogs(token="test-token", cache=True)
        client.uploads.get(1).status  # noqa: B018 — triggers resolve
        with client.cache_only(), pytest.raises(CacheMissError):
            client.uploads.get(1).status  # noqa: B018 — triggers resolve
        assert route.call_count == 1
        client.close()
