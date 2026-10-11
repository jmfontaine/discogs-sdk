"""Tests for sync Uploads resource."""

from __future__ import annotations

import pytest
import respx

from discogs_sdk import Discogs
from discogs_sdk._exceptions import CacheMissError, DiscogsAPIError
from tests.conftest import (
    BASE_URL,
    StoreRecordingCache,
    make_paginated_response,
    make_release,
    make_upload,
    make_upload_completed,
)


def _multipart_without_boundary(request) -> bytes:
    """The request's multipart body with its random boundary blanked out."""
    boundary = request.headers["Content-Type"].split("boundary=")[1].encode()
    return request.content.replace(boundary, b"BOUNDARY")


_LOCATION = {"Location": "https://api.discogs.com/inventory/upload/599632"}
_ROUTES = [
    pytest.param("create", "/inventory/upload/add", id="create"),
    pytest.param("change", "/inventory/upload/change", id="change"),
    pytest.param("delete", "/inventory/upload/delete", id="delete"),
]


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "inventory.csv"
    path.write_text("header\nrow1")
    return path


class TestUploadsCreate:
    def test_create(self, client, respx_mock, csv_file):
        respx_mock.post("/inventory/upload/add").respond(200, headers=_LOCATION)
        assert client.uploads.create(file=str(csv_file)) == 599632

    def test_create_error(self, client, respx_mock, csv_file):
        respx_mock.post("/inventory/upload/add").respond(400, json={"message": "Bad"})
        with pytest.raises(DiscogsAPIError) as exc_info:
            client.uploads.create(file=str(csv_file))
        assert exc_info.value.status_code == 400

    def test_path_posts_the_same_multipart_body_as_str(
        self, client, respx_mock, tmp_path
    ):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("release_id,price\n352665,25.00\n")
        route = respx_mock.post("/inventory/upload/add").respond(200, headers=_LOCATION)
        client.uploads.create(file=csv_file)
        client.uploads.create(file=str(csv_file))
        bodies = [_multipart_without_boundary(call.request) for call in route.calls]
        assert bodies[0] == bodies[1]
        assert (
            b'Content-Disposition: form-data; name="upload"; filename="inventory.csv"'
            b"\r\nContent-Type: text/csv\r\n\r\nrelease_id,price\n352665,25.00\n"
        ) in bodies[0]


class TestUploadsChange:
    def test_change(self, client, respx_mock, csv_file):
        respx_mock.post("/inventory/upload/change").respond(200, headers=_LOCATION)
        assert client.uploads.change(file=str(csv_file)) == 599632

    def test_change_error(self, client, respx_mock, csv_file):
        respx_mock.post("/inventory/upload/change").respond(
            400, json={"message": "Bad"}
        )
        with pytest.raises(DiscogsAPIError) as exc_info:
            client.uploads.change(file=str(csv_file))
        assert exc_info.value.status_code == 400


class TestUploadsDelete:
    def test_delete(self, client, respx_mock, csv_file):
        respx_mock.post("/inventory/upload/delete").respond(200, headers=_LOCATION)
        assert client.uploads.delete(file=str(csv_file)) == 599632

    def test_delete_error(self, client, respx_mock, csv_file):
        respx_mock.post("/inventory/upload/delete").respond(
            400, json={"message": "Bad"}
        )
        with pytest.raises(DiscogsAPIError) as exc_info:
            client.uploads.delete(file=str(csv_file))
        assert exc_info.value.status_code == 400


@pytest.mark.parametrize(("method", "path"), _ROUTES)
class TestUploadJobId:
    @pytest.mark.parametrize(
        "location",
        ["/inventory/upload/7", "/inventory/upload/7/", "/inventory/upload/7?x=1"],
    )
    def test_relative_or_decorated_location(
        self, client, respx_mock, csv_file, method, path, location
    ):
        respx_mock.post(path).respond(200, headers={"Location": location})
        assert getattr(client.uploads, method)(file=csv_file) == 7

    @pytest.mark.parametrize(
        "headers",
        [
            pytest.param({}, id="missing"),
            pytest.param({"Location": ""}, id="empty"),
            pytest.param({"Location": "/inventory/upload/abc"}, id="abc"),
            pytest.param({"Location": "/inventory/upload/"}, id="none"),
        ],
    )
    def test_response_without_a_job_id_raises(
        self, client, respx_mock, csv_file, method, path, headers
    ):
        respx_mock.post(path).respond(200, headers=headers, text="queued")
        with pytest.raises(DiscogsAPIError, match="Location") as exc_info:
            getattr(client.uploads, method)(file=csv_file)
        error = exc_info.value
        assert type(error) is DiscogsAPIError
        assert error.status_code == 200
        assert error.response_body == "queued"
        assert "uploads.list()" in str(error)
        assert error.method == "POST"
        assert error.url == f"{BASE_URL}{path}"
        assert error.ratelimit is None


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
