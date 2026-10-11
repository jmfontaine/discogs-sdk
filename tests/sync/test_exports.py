"""Tests for sync Exports resource."""

from __future__ import annotations

import httpx2
import pytest
import respx

from discogs_sdk import Discogs
from discogs_sdk._exceptions import (
    CacheMissError,
    DiscogsAPIError,
    DiscogsConnectionError,
)
from discogs_sdk.models.export import Export
from tests.conftest import (
    StoreRecordingCache,
    make_export,
    make_paginated_response,
    make_release,
)


class TestExportsRequest:
    def test_request_success(self, client, respx_mock):
        respx_mock.post("/inventory/export").mock(return_value=respx.MockResponse(200))
        client.exports.request()

    def test_request_error(self, client, respx_mock):
        respx_mock.post("/inventory/export").mock(
            return_value=respx.MockResponse(403, json={"message": "Forbidden"})
        )
        with pytest.raises(DiscogsAPIError):
            client.exports.request()


class TestExportsList:
    def test_list(self, client, respx_mock):
        respx_mock.get("/inventory/export").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("items", [make_export()])
            )
        )
        results = list(client.exports.list())
        assert len(results) == 1
        assert isinstance(results[0], Export)


class TestExportsGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.exports.get(1)
        assert respx_mock.calls.call_count == 0

    def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/inventory/export/1").mock(
            return_value=respx.MockResponse(200, json=make_export())
        )
        lazy = client.exports.get(1)
        assert lazy.id == 1


class TestExportStatusPolling:
    """A status poll has to see the job finish, so it never touches the cache."""

    def test_each_get_reaches_the_api(self, respx_mock):
        route = respx_mock.get("/inventory/export/1").mock(
            side_effect=[
                respx.MockResponse(200, json=make_export(status="pending")),
                respx.MockResponse(200, json=make_export(status="completed")),
            ]
        )
        client = Discogs(token="test-token", cache=True)
        assert client.exports.get(1).status == "pending"
        assert client.exports.get(1).status == "completed"
        assert route.call_count == 2
        client.close()

    def test_poll_stores_nothing(self, respx_mock):
        respx_mock.get("/inventory/export/1").respond(200, json=make_export())
        cache = StoreRecordingCache()
        events = []
        client = Discogs(token="test-token", cache=cache, on_request=events.append)
        client.exports.get(1).status  # noqa: B018 — triggers resolve
        client.close()
        assert cache.stored_keys == []
        assert [(e.source, e.stored) for e in events] == [("network", False)]

    def test_other_resources_stay_cached(self, respx_mock):
        respx_mock.get("/inventory/export/1").respond(200, json=make_export())
        route = respx_mock.get("/releases/352665").respond(200, json=make_release())
        client = Discogs(token="test-token", cache=True)
        client.exports.get(1).status  # noqa: B018 — triggers resolve
        client.releases.get(352665).title  # noqa: B018 — triggers resolve
        client.releases.get(352665).title  # noqa: B018 — triggers resolve
        assert route.call_count == 1
        client.close()

    def test_cache_only_has_nothing_to_serve(self, respx_mock):
        route = respx_mock.get("/inventory/export/1").respond(200, json=make_export())
        client = Discogs(token="test-token", cache=True)
        client.exports.get(1).status  # noqa: B018 — triggers resolve
        with client.cache_only(), pytest.raises(CacheMissError):
            client.exports.get(1).status  # noqa: B018 — triggers resolve
        assert route.call_count == 1
        client.close()


class TestExportsDownload:
    def test_download_returns_bytes(self, client, respx_mock):
        respx_mock.get("/inventory/export/1/download").mock(
            return_value=respx.MockResponse(200, content=b"csv,data,here")
        )
        result = client.exports.download(1)
        assert result == b"csv,data,here"

    def test_download_error(self, client, respx_mock):
        respx_mock.get("/inventory/export/999/download").mock(
            return_value=respx.MockResponse(404, text="Not Found")
        )
        with pytest.raises(DiscogsAPIError):
            client.exports.download(999)

    def test_download_connect_error(self, no_retry_client, respx_mock):
        respx_mock.get("/inventory/export/1/download").mock(
            side_effect=httpx2.ConnectError("Connection refused")
        )
        with pytest.raises(DiscogsConnectionError):
            no_retry_client.exports.download(1)
