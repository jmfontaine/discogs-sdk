"""Tests for sync retry logic in _send()."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import respx

from discogs_sdk import Discogs
from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._exceptions import DiscogsAPIError, DiscogsConnectionError, RateLimitError
from discogs_sdk.models.release import Release

from tests.conftest import BASE_URL, make_paginated_response, make_release


@pytest.fixture
def respx_mock():
    with respx.mock(base_url=BASE_URL) as router:
        yield router


@pytest.fixture
def client(respx_mock):
    return Discogs(token="test-token", max_retries=3)


class TestRetryOn429:
    def test_retries_then_succeeds(self, client, respx_mock):
        responses = iter(
            [
                httpx.Response(429, json={"message": "Rate limited"}),
                httpx.Response(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))

        with patch("time.sleep") as mock_sleep:
            lazy = client.releases.get(1)
            assert lazy.title == "The Downward Spiral"

        assert mock_sleep.call_count == 1

    def test_respects_retry_after_header(self, client, respx_mock):
        responses = iter(
            [
                httpx.Response(429, json={"message": "Rate limited"}, headers={"Retry-After": "5"}),
                httpx.Response(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))

        with patch("time.sleep") as mock_sleep:
            lazy = client.releases.get(1)
            lazy.title  # noqa: B018 — triggers sync resolve

        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] == 5.0

    def test_exhausts_retries_raises_rate_limit_error(self, client, respx_mock):
        respx_mock.get("/releases/1").mock(
            return_value=httpx.Response(429, json={"message": "Rate limited"}, headers={"Retry-After": "10"}),
        )

        with patch("time.sleep"):
            lazy = client.releases.get(1)
            with pytest.raises(RateLimitError) as exc_info:
                lazy.title  # noqa: B018
            assert exc_info.value.retry_after == "10"


class TestRetryOn5xx:
    def test_retries_then_succeeds(self, client, respx_mock):
        responses = iter(
            [
                httpx.Response(502, text="Bad Gateway"),
                httpx.Response(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))

        with patch("time.sleep"):
            lazy = client.releases.get(1)
            assert lazy.title == "The Downward Spiral"

    def test_exhausts_retries_raises_api_error(self, client, respx_mock):
        respx_mock.get("/releases/1").mock(
            return_value=httpx.Response(500, json={"message": "Internal Server Error"}),
        )

        with patch("time.sleep"):
            lazy = client.releases.get(1)
            with pytest.raises(DiscogsAPIError):
                lazy.title  # noqa: B018


class TestRetryOnConnectionError:
    def test_retries_then_succeeds(self, client, respx_mock):
        call_count = 0

        def side_effect(req):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(200, json=make_release())

        respx_mock.get("/releases/1").mock(side_effect=side_effect)

        with patch("time.sleep"):
            lazy = client.releases.get(1)
            assert lazy.title == "The Downward Spiral"

    def test_timeout_retries_then_succeeds(self, client, respx_mock):
        call_count = 0

        def side_effect(req):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("Timed out")
            return httpx.Response(200, json=make_release())

        respx_mock.get("/releases/1").mock(side_effect=side_effect)

        with patch("time.sleep"):
            lazy = client.releases.get(1)
            assert lazy.title == "The Downward Spiral"

    def test_exhausts_retries_raises_connection_error(self, respx_mock):
        client = Discogs(token="test-token", max_retries=1)
        respx_mock.get("/releases/1").mock(side_effect=httpx.ConnectError("Connection refused"))

        with patch("time.sleep"):
            lazy = client.releases.get(1)
            with pytest.raises(DiscogsConnectionError, match="Connection refused"):
                lazy.title  # noqa: B018

    def test_timeout_exhausts_retries_raises_connection_error(self, respx_mock):
        client = Discogs(token="test-token", max_retries=1)
        respx_mock.get("/releases/1").mock(side_effect=httpx.TimeoutException("Timed out"))

        with patch("time.sleep"):
            lazy = client.releases.get(1)
            with pytest.raises(DiscogsConnectionError, match="Timed out"):
                lazy.title  # noqa: B018


class TestMaxRetriesZero:
    def test_no_retry_on_429(self, respx_mock):
        client = Discogs(token="test-token", max_retries=0)
        respx_mock.get("/releases/1").mock(
            return_value=httpx.Response(429, json={"message": "Rate limited"}),
        )

        lazy = client.releases.get(1)
        with pytest.raises(RateLimitError):
            lazy.title  # noqa: B018

    def test_no_retry_on_connect_error(self, respx_mock):
        client = Discogs(token="test-token", max_retries=0)
        respx_mock.get("/releases/1").mock(side_effect=httpx.ConnectError("Connection refused"))

        lazy = client.releases.get(1)
        with pytest.raises(DiscogsConnectionError):
            lazy.title  # noqa: B018


class TestRetryCoversLazy:
    def test_lazy_resolve_retries(self, client, respx_mock):
        responses = iter(
            [
                httpx.Response(429, json={"message": "Rate limited"}),
                httpx.Response(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))

        with patch("time.sleep"):
            lazy = LazyResource(
                client=client,
                path="/releases/1",
                model_cls=Release,
            )
            assert lazy.title == "The Downward Spiral"


class TestRetryConversPaginator:
    def test_paginator_fetch_retries(self, client, respx_mock):
        page_body = make_paginated_response("releases", [make_release()])
        responses = iter(
            [
                httpx.Response(503, text="Service Unavailable"),
                httpx.Response(200, json=page_body),
            ]
        )
        respx_mock.get("/releases").mock(side_effect=lambda req: next(responses))

        with patch("time.sleep"):
            page = SyncPage(
                client=client,
                path="/releases",
                params={},
                model_cls=Release,
                items_key="releases",
            )
            results = list(page)
            assert len(results) == 1


class TestRetryCoversPostFile:
    def test_post_file_retries(self, client, respx_mock, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("header\nrow1\n")

        responses = iter(
            [
                httpx.Response(502, text="Bad Gateway"),
                httpx.Response(200, json={}),
            ]
        )
        respx_mock.post("/inventory/upload/add").mock(side_effect=lambda req: next(responses))

        with patch("time.sleep"):
            client.uploads.create(file=str(csv_file))
