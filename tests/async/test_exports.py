"""Tests for async Exports resource."""

from __future__ import annotations

import httpx2
import pytest
import respx

from discogs_sdk import AsyncDiscogs, RateLimit
from discogs_sdk._exceptions import (
    CacheMissError,
    DiscogsAPIError,
    DiscogsConnectionError,
    ForbiddenError,
)
from discogs_sdk.models.export import Export
from tests.conftest import (
    BASE_URL,
    SpyCache,
    make_export,
    make_paginated_response,
    make_release,
)

_LOCATION = "https://api.discogs.com/inventory/export/599632"
_NO_JOB_ID = [
    pytest.param({}, id="missing"),
    pytest.param({"Location": ""}, id="empty"),
    pytest.param(
        {"Location": "https://api.discogs.com/inventory/export/abc"}, id="abc"
    ),
    pytest.param({"Location": "https://api.discogs.com/inventory/export/"}, id="none"),
    pytest.param(
        [(b"Location", "/inventory/export/\u0667".encode())], id="non-ascii-digit"
    ),
    pytest.param({"Location": "http://[::1/inventory/export/7"}, id="bad-authority"),
]


class TestExportsRequest:
    async def test_request_success(self, client, respx_mock):
        respx_mock.post("/inventory/export").respond(
            200, headers={"Location": _LOCATION}
        )
        assert await client.exports.request() == 599632

    @pytest.mark.parametrize(
        "location",
        [
            "/inventory/export/7",
            "/inventory/export/7/",
            "https://api.discogs.com/inventory/export/7?page=1",
        ],
    )
    async def test_relative_or_decorated_location(self, client, respx_mock, location):
        respx_mock.post("/inventory/export").respond(
            200, headers={"Location": location}
        )
        assert await client.exports.request() == 7

    @pytest.mark.parametrize("headers", _NO_JOB_ID)
    async def test_response_without_a_job_id_raises(self, client, respx_mock, headers):
        respx_mock.post("/inventory/export").respond(
            200, headers=headers, text="queued"
        )
        with pytest.raises(DiscogsAPIError, match="Location") as exc_info:
            await client.exports.request()
        error = exc_info.value
        assert type(error) is DiscogsAPIError
        assert error.status_code == 200
        assert error.response_body == "queued"
        assert "exports.list()" in str(error)
        assert error.method == "POST"
        assert error.url == f"{BASE_URL}/inventory/export"
        assert error.ratelimit is None

    async def test_job_id_error_carries_the_rate_limit(self, client, respx_mock):
        respx_mock.post("/inventory/export").respond(
            200,
            headers={
                "X-Discogs-Ratelimit": "60",
                "X-Discogs-Ratelimit-Used": "14",
                "X-Discogs-Ratelimit-Remaining": "46",
            },
        )
        with pytest.raises(DiscogsAPIError, match="Location") as exc_info:
            await client.exports.request()
        assert exc_info.value.ratelimit == RateLimit(60, 14, 46)

    async def test_long_malformed_location_is_quoted_bounded(self, client, respx_mock):
        # Control characters, which repr() expands fourfold.
        location = b"/inventory/export/" + b"\x85" * 10_000
        respx_mock.post("/inventory/export").respond(
            200, headers=[(b"Location", location)]
        )
        with pytest.raises(DiscogsAPIError, match="Location") as exc_info:
            await client.exports.request()
        assert len(str(exc_info.value)) < 500

    @pytest.mark.parametrize(
        ("status", "error_cls"), [(403, ForbiddenError), (409, DiscogsAPIError)]
    )
    async def test_http_error_is_mapped_first(
        self, client, respx_mock, status, error_cls
    ):
        respx_mock.post("/inventory/export").respond(
            status, json={"message": "No"}, headers={"Location": _LOCATION}
        )
        with pytest.raises(error_cls) as exc_info:
            await client.exports.request()
        assert exc_info.value.status_code == status
        assert "Location" not in str(exc_info.value)


class TestExportsList:
    async def test_list(self, client, respx_mock):
        route = respx_mock.get("/inventory/export").mock(
            return_value=respx.MockResponse(
                200, json=make_paginated_response("items", [make_export()])
            )
        )
        results = [item async for item in client.exports.list(page=2, per_page=50)]
        assert len(results) == 1
        assert isinstance(results[0], Export)
        params = route.calls.last.request.url.params
        assert params["page"] == "2"
        assert params["per_page"] == "50"


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
        cache = SpyCache()
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

    async def test_download_error(self, client, respx_mock):
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
