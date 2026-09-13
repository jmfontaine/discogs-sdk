"""Tests for async retry logic in _send()."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx2
import pytest
import respx

from discogs_sdk import AsyncDiscogs
from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._exceptions import (
    DiscogsAPIError,
    DiscogsConnectionError,
    RateLimitError,
)
from discogs_sdk.models.release import Release
from tests.conftest import BASE_URL, make_listing, make_paginated_response, make_release


@pytest.fixture
def respx_mock():
    with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
        yield router


@pytest.fixture
def client(respx_mock):
    return AsyncDiscogs(token="test-token", max_retries=3)


class TestRetryOn429:
    async def test_retries_then_succeeds(self, client, respx_mock):
        responses = iter(
            [
                respx.MockResponse(429, json={"message": "Rate limited"}),
                respx.MockResponse(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await client.releases.get(1)

        assert isinstance(result, Release)
        assert mock_sleep.call_count == 1

    async def test_respects_retry_after_header(self, client, respx_mock):
        responses = iter(
            [
                respx.MockResponse(
                    429, json={"message": "Rate limited"}, headers={"Retry-After": "5"}
                ),
                respx.MockResponse(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await client.releases.get(1)

        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] == 5.0

    async def test_exhausts_retries_raises_rate_limit_error(self, client, respx_mock):
        respx_mock.get("/releases/1").mock(
            return_value=respx.MockResponse(
                429, json={"message": "Rate limited"}, headers={"Retry-After": "10"}
            ),
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            lazy = client.releases.get(1)
            with pytest.raises(RateLimitError) as exc_info:
                await lazy
            assert exc_info.value.retry_after == "10"


class TestRetryOn5xx:
    async def test_retries_then_succeeds(self, client, respx_mock):
        responses = iter(
            [
                respx.MockResponse(502, text="Bad Gateway"),
                respx.MockResponse(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.releases.get(1)

        assert isinstance(result, Release)

    async def test_exhausts_retries_raises_api_error(self, client, respx_mock):
        respx_mock.get("/releases/1").mock(
            return_value=respx.MockResponse(
                500, json={"message": "Internal Server Error"}
            ),
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            lazy = client.releases.get(1)
            with pytest.raises(DiscogsAPIError):
                await lazy


class TestRetryOnConnectionError:
    async def test_retries_then_succeeds(self, client, respx_mock):
        call_count = 0

        def side_effect(req):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx2.ConnectError("Connection refused")
            return respx.MockResponse(200, json=make_release())

        respx_mock.get("/releases/1").mock(side_effect=side_effect)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.releases.get(1)

        assert isinstance(result, Release)

    async def test_timeout_retries_then_succeeds(self, client, respx_mock):
        call_count = 0

        def side_effect(req):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx2.TimeoutException("Timed out")
            return respx.MockResponse(200, json=make_release())

        respx_mock.get("/releases/1").mock(side_effect=side_effect)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.releases.get(1)

        assert isinstance(result, Release)

    async def test_exhausts_retries_raises_connection_error(self, respx_mock):
        client = AsyncDiscogs(token="test-token", max_retries=1)
        respx_mock.get("/releases/1").mock(
            side_effect=httpx2.ConnectError("Connection refused")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            lazy = client.releases.get(1)
            with pytest.raises(DiscogsConnectionError, match="Connection refused"):
                await lazy

    async def test_timeout_exhausts_retries_raises_connection_error(self, respx_mock):
        client = AsyncDiscogs(token="test-token", max_retries=1)
        respx_mock.get("/releases/1").mock(
            side_effect=httpx2.TimeoutException("Timed out")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            lazy = client.releases.get(1)
            with pytest.raises(DiscogsConnectionError, match="Timed out"):
                await lazy


class TestMaxRetriesZero:
    async def test_no_retry_on_429(self, respx_mock):
        client = AsyncDiscogs(token="test-token", max_retries=0)
        respx_mock.get("/releases/1").mock(
            return_value=respx.MockResponse(429, json={"message": "Rate limited"}),
        )

        lazy = client.releases.get(1)
        with pytest.raises(RateLimitError):
            await lazy

    async def test_no_retry_on_connect_error(self, respx_mock):
        client = AsyncDiscogs(token="test-token", max_retries=0)
        respx_mock.get("/releases/1").mock(
            side_effect=httpx2.ConnectError("Connection refused")
        )

        lazy = client.releases.get(1)
        with pytest.raises(DiscogsConnectionError):
            await lazy


class TestRetryCoversLazy:
    async def test_lazy_resolve_retries(self, client, respx_mock):
        responses = iter(
            [
                respx.MockResponse(429, json={"message": "Rate limited"}),
                respx.MockResponse(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.releases.get(1)
            assert isinstance(result, Release)


class TestRetryCoversPaginator:
    async def test_paginator_fetch_retries(self, client, respx_mock):
        page_body = make_paginated_response("releases", [make_release()])
        responses = iter(
            [
                respx.MockResponse(503, text="Service Unavailable"),
                respx.MockResponse(200, json=page_body),
            ]
        )
        respx_mock.get("/releases").mock(side_effect=lambda req: next(responses))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            page = AsyncPage(
                client=client,
                path="/releases",
                params={},
                model_cls=Release,
                items_key="releases",
            )
            results = [item async for item in page]
            assert len(results) == 1


class TestWriteRetrySafety:
    """A mutation that may already have been committed must never be replayed."""

    async def test_read_timeout_does_not_replay_a_create(self, client, respx_mock):
        created: list[dict] = []

        def side_effect(request):
            # The server commits, then the response is lost on the way back.
            created.append({"listing_id": 1 + len(created)})
            raise httpx2.ReadTimeout("Timed out reading response")

        route = respx_mock.post("/marketplace/listings").mock(side_effect=side_effect)

        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            pytest.raises(DiscogsConnectionError, match="Timed out reading response"),
        ):
            await client.marketplace.listings.create(
                release_id=352665, condition="Mint (M)", price=29.99
            )

        assert len(created) == 1
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    async def test_server_error_does_not_replay_a_file_upload(
        self, client, respx_mock, tmp_path
    ):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("release_id,price\n352665,29.99\n")
        route = respx_mock.post("/inventory/upload/add").mock(
            return_value=respx.MockResponse(502, json={"message": "Bad Gateway"})
        )

        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            pytest.raises(DiscogsAPIError) as exc_info,
        ):
            await client.uploads.create(file=str(csv_file))

        assert exc_info.value.status_code == 502
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    async def test_delete_is_not_replayed_after_a_server_error(
        self, client, respx_mock
    ):
        route = respx_mock.delete("/marketplace/listings/1").mock(
            return_value=respx.MockResponse(
                503, json={"message": "Service Unavailable"}
            )
        )

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(DiscogsAPIError),
        ):
            await client.marketplace.listings.delete(1)

        assert route.call_count == 1

    async def test_connection_failure_before_send_is_retried(self, client, respx_mock):
        responses = iter(
            [
                httpx2.ConnectError("Connection refused"),
                respx.MockResponse(201, json=make_listing()),
            ]
        )

        def side_effect(request):
            result = next(responses)
            if isinstance(result, Exception):
                raise result
            return result

        route = respx_mock.post("/marketplace/listings").mock(side_effect=side_effect)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await client.marketplace.listings.create(
                release_id=352665, condition="Mint (M)", price=29.99
            )

        assert route.call_count == 2
        assert mock_sleep.call_count == 1

    async def test_read_error_is_mapped_and_retried_for_reads(self, client, respx_mock):
        responses = iter(
            [
                httpx2.ReadError("connection reset"),
                respx.MockResponse(200, json=make_release()),
            ]
        )

        def side_effect(request):
            result = next(responses)
            if isinstance(result, Exception):
                raise result
            return result

        route = respx_mock.get("/releases/1").mock(side_effect=side_effect)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await client.releases.get(1)

        assert route.call_count == 2

    async def test_read_error_does_not_replay_a_write(self, client, respx_mock):
        route = respx_mock.post("/marketplace/listings").mock(
            side_effect=httpx2.ReadError("connection reset")
        )

        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            pytest.raises(DiscogsConnectionError),
        ):
            await client.marketplace.listings.create(
                release_id=352665, condition="Mint (M)", price=29.99
            )

        assert route.call_count == 1
        mock_sleep.assert_not_called()
