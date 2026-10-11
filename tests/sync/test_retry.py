"""Tests for sync retry logic in _send()."""

from __future__ import annotations

import re
from unittest.mock import patch

import httpx2
import pytest
import respx

from discogs_sdk import Discogs
from discogs_sdk._events import RequestEvent
from discogs_sdk._exceptions import (
    DiscogsAPIError,
    DiscogsConnectionError,
    RateLimitError,
)
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk.models.release import Release
from tests.conftest import BASE_URL, make_listing, make_paginated_response, make_release


@pytest.fixture
def respx_mock():
    with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
        yield router


@pytest.fixture
def client(respx_mock):
    return Discogs(token="test-token", max_retries=3)


class TestRetryOn429:
    def test_retries_then_succeeds(self, client, respx_mock):
        responses = iter(
            [
                respx.MockResponse(429, json={"message": "Rate limited"}),
                respx.MockResponse(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))

        with patch("time.sleep") as mock_sleep:
            lazy = client.releases.get(1)
            assert lazy.title == "The Downward Spiral"

        assert mock_sleep.call_count == 1

    @pytest.mark.parametrize("seconds", ["30", "60"])  # 60: the cap is inclusive
    def test_respects_retry_after_header(self, client, respx_mock, seconds):
        responses = iter(
            [
                respx.MockResponse(
                    429,
                    json={"message": "Rate limited"},
                    headers={"Retry-After": seconds},
                ),
                respx.MockResponse(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))

        with patch("time.sleep") as mock_sleep:
            lazy = client.releases.get(1)
            lazy.title  # noqa: B018 — triggers sync resolve

        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] == float(seconds)

    def test_exhausts_retries_raises_rate_limit_error(self, client, respx_mock):
        respx_mock.get("/releases/1").mock(
            return_value=respx.MockResponse(
                429, json={"message": "Rate limited"}, headers={"Retry-After": "10"}
            ),
        )

        with patch("time.sleep"):
            lazy = client.releases.get(1)
            with pytest.raises(RateLimitError) as exc_info:
                lazy.title  # noqa: B018
            assert exc_info.value.retry_after == "10"


class TestRetryAfterCap:
    """A valid Retry-After above MAX_RETRY_AFTER surfaces instead of waiting."""

    def test_long_rate_limit_raises_without_waiting(self, respx_mock):
        events: list[RequestEvent] = []
        client = Discogs(token="test-token", max_retries=3, on_request=events.append)
        route = respx_mock.get("/releases/1").mock(
            return_value=respx.MockResponse(
                429, json={"message": "Rate limited"}, headers={"Retry-After": "3600"}
            ),
        )

        with patch("time.sleep") as mock_sleep:
            lazy = client.releases.get(1)
            with pytest.raises(RateLimitError) as exc_info:
                lazy.title  # noqa: B018

        assert route.call_count == 1
        mock_sleep.assert_not_called()
        assert exc_info.value.retry_after == "3600"
        assert [(e.status_code, e.attempts) for e in events] == [(429, 1)]

    def test_long_server_error_raises_without_waiting(self, client, respx_mock):
        route = respx_mock.get("/releases/1").mock(
            return_value=respx.MockResponse(
                503, text="Service Unavailable", headers={"Retry-After": "3600"}
            ),
        )

        with patch("time.sleep") as mock_sleep:
            lazy = client.releases.get(1)
            with pytest.raises(DiscogsAPIError) as exc_info:
                lazy.title  # noqa: B018

        assert route.call_count == 1
        mock_sleep.assert_not_called()
        assert exc_info.value.status_code == 503

    def test_invalid_value_backs_off(self, client, respx_mock):
        responses = iter(
            [
                respx.MockResponse(
                    429, json={"message": "Rate limited"}, headers={"Retry-After": "-5"}
                ),
                respx.MockResponse(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))

        with patch("time.sleep") as mock_sleep:
            assert client.releases.get(1).title == "The Downward Spiral"

        mock_sleep.assert_called_once()
        assert 1.0 <= mock_sleep.call_args[0][0] < 2.0


class TestRetryOn5xx:
    def test_retries_then_succeeds(self, client, respx_mock):
        responses = iter(
            [
                respx.MockResponse(502, text="Bad Gateway"),
                respx.MockResponse(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))

        with patch("time.sleep"):
            lazy = client.releases.get(1)
            assert lazy.title == "The Downward Spiral"

    def test_exhausts_retries_raises_api_error(self, client, respx_mock):
        respx_mock.get("/releases/1").mock(
            return_value=respx.MockResponse(
                500, json={"message": "Internal Server Error"}
            ),
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
                raise httpx2.ConnectError("Connection refused")
            return respx.MockResponse(200, json=make_release())

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
                raise httpx2.TimeoutException("Timed out")
            return respx.MockResponse(200, json=make_release())

        respx_mock.get("/releases/1").mock(side_effect=side_effect)

        with patch("time.sleep"):
            lazy = client.releases.get(1)
            assert lazy.title == "The Downward Spiral"

    def test_exhausts_retries_raises_connection_error(self, respx_mock):
        client = Discogs(token="test-token", max_retries=1)
        respx_mock.get("/releases/1").mock(
            side_effect=httpx2.ConnectError("Connection refused")
        )

        with patch("time.sleep"):
            lazy = client.releases.get(1)
            with pytest.raises(DiscogsConnectionError, match="Connection refused"):
                lazy.title  # noqa: B018

    def test_timeout_exhausts_retries_raises_connection_error(self, respx_mock):
        client = Discogs(token="test-token", max_retries=1)
        respx_mock.get("/releases/1").mock(
            side_effect=httpx2.TimeoutException("Timed out")
        )

        with patch("time.sleep"):
            lazy = client.releases.get(1)
            with pytest.raises(DiscogsConnectionError, match="Timed out"):
                lazy.title  # noqa: B018


class TestMaxRetriesZero:
    def test_no_retry_on_429(self, respx_mock):
        client = Discogs(token="test-token", max_retries=0)
        respx_mock.get("/releases/1").mock(
            return_value=respx.MockResponse(429, json={"message": "Rate limited"}),
        )

        lazy = client.releases.get(1)
        with pytest.raises(RateLimitError):
            lazy.title  # noqa: B018

    def test_no_retry_on_connect_error(self, respx_mock):
        client = Discogs(token="test-token", max_retries=0)
        respx_mock.get("/releases/1").mock(
            side_effect=httpx2.ConnectError("Connection refused")
        )

        lazy = client.releases.get(1)
        with pytest.raises(DiscogsConnectionError):
            lazy.title  # noqa: B018


class TestRetryCoversLazy:
    def test_lazy_resolve_retries(self, client, respx_mock):
        responses = iter(
            [
                respx.MockResponse(429, json={"message": "Rate limited"}),
                respx.MockResponse(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))

        with patch("time.sleep"):
            assert client.releases.get(1).title == "The Downward Spiral"


class TestRetryCoversPaginator:
    def test_paginator_fetch_retries(self, client, respx_mock):
        page_body = make_paginated_response("releases", [make_release()])
        responses = iter(
            [
                respx.MockResponse(503, text="Service Unavailable"),
                respx.MockResponse(200, json=page_body),
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


class TestWriteRetrySafety:
    """A mutation that may already have been committed must never be replayed."""

    def test_read_timeout_does_not_replay_a_create(self, client, respx_mock):
        created: list[dict] = []

        def side_effect(request):
            # The server commits, then the response is lost on the way back.
            created.append({"listing_id": 1 + len(created)})
            raise httpx2.ReadTimeout("Timed out reading response")

        route = respx_mock.post("/marketplace/listings").mock(side_effect=side_effect)

        with (
            patch("time.sleep") as mock_sleep,
            pytest.raises(DiscogsConnectionError, match="Timed out reading response"),
        ):
            client.marketplace.listings.create(
                release_id=352665, condition="Mint (M)", price=29.99
            )

        assert len(created) == 1
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    def test_server_error_does_not_replay_a_file_upload(
        self, client, respx_mock, tmp_path
    ):
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("release_id,price\n352665,29.99\n")
        route = respx_mock.post("/inventory/upload/add").mock(
            return_value=respx.MockResponse(502, json={"message": "Bad Gateway"})
        )

        with (
            patch("time.sleep") as mock_sleep,
            pytest.raises(DiscogsAPIError) as exc_info,
        ):
            client.uploads.create(file=str(csv_file))

        assert exc_info.value.status_code == 502
        assert route.call_count == 1
        mock_sleep.assert_not_called()

    def test_delete_is_not_replayed_after_a_server_error(self, client, respx_mock):
        route = respx_mock.delete("/marketplace/listings/1").mock(
            return_value=respx.MockResponse(
                503, json={"message": "Service Unavailable"}
            )
        )

        with patch("time.sleep"), pytest.raises(DiscogsAPIError):
            client.marketplace.listings.delete(1)

        assert route.call_count == 1

    def test_connection_failure_before_send_is_retried(self, client, respx_mock):
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

        with patch("time.sleep") as mock_sleep:
            client.marketplace.listings.create(
                release_id=352665, condition="Mint (M)", price=29.99
            )

        assert route.call_count == 2
        assert mock_sleep.call_count == 1

    def test_read_error_is_mapped_and_retried_for_reads(self, client, respx_mock):
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

        with patch("time.sleep"):
            _ = client.releases.get(1).title

        assert route.call_count == 2

    def test_read_error_does_not_replay_a_write(self, client, respx_mock):
        route = respx_mock.post("/marketplace/listings").mock(
            side_effect=httpx2.ReadError("connection reset")
        )

        with patch("time.sleep") as mock_sleep, pytest.raises(DiscogsConnectionError):
            client.marketplace.listings.create(
                release_id=352665, condition="Mint (M)", price=29.99
            )

        assert route.call_count == 1
        mock_sleep.assert_not_called()


class TestTransportErrorBoundary:
    """Every httpx2 RequestError surfaces as DiscogsConnectionError."""

    def test_dropped_keep_alive_exhausts_retries_for_reads(self, respx_mock):
        client = Discogs(token="test-token", max_retries=2)
        original = httpx2.RemoteProtocolError(
            "Server disconnected without sending a response."
        )
        route = respx_mock.get("/releases/1").mock(side_effect=original)

        with (
            patch("time.sleep"),
            pytest.raises(DiscogsConnectionError) as exc_info,
        ):
            client.releases.get(1).title  # noqa: B018

        assert route.call_count == 3
        assert exc_info.value.__cause__ is original

    def test_dropped_keep_alive_is_retried_for_reads(self, client, respx_mock):
        responses = iter(
            [
                httpx2.RemoteProtocolError(
                    "Server disconnected without sending a response."
                ),
                respx.MockResponse(200, json=make_release()),
            ]
        )

        def side_effect(request):
            result = next(responses)
            if isinstance(result, Exception):
                raise result
            return result

        route = respx_mock.get("/releases/1").mock(side_effect=side_effect)

        with patch("time.sleep"):
            assert client.releases.get(1).title == "The Downward Spiral"

        assert route.call_count == 2

    def test_dropped_keep_alive_does_not_replay_a_write(self, client, respx_mock):
        original = httpx2.RemoteProtocolError(
            "Server disconnected without sending a response."
        )
        route = respx_mock.post("/marketplace/listings").mock(side_effect=original)

        with (
            patch("time.sleep") as mock_sleep,
            pytest.raises(DiscogsConnectionError) as exc_info,
        ):
            client.marketplace.listings.create(
                release_id=352665, condition="Mint (M)", price=29.99
            )

        assert route.call_count == 1
        assert exc_info.value.__cause__ is original
        mock_sleep.assert_not_called()

    @pytest.mark.parametrize(
        "error",
        [
            httpx2.LocalProtocolError("Illegal header value"),
            httpx2.UnsupportedProtocol("Request URL has an unsupported protocol"),
            httpx2.ProxyError("407 Proxy Authentication Required"),
            httpx2.DecodingError("Error -3 while decompressing data"),
            httpx2.TooManyRedirects("Exceeded maximum allowed redirects."),
        ],
        ids=lambda error: type(error).__name__,
    )
    def test_deterministic_failures_are_mapped_not_retried(
        self, client, respx_mock, error
    ):
        route = respx_mock.get("/releases/1").mock(side_effect=error)

        with (
            patch("time.sleep") as mock_sleep,
            pytest.raises(DiscogsConnectionError) as exc_info,
        ):
            client.releases.get(1).title  # noqa: B018

        assert route.call_count == 1
        assert exc_info.value.__cause__ is error
        mock_sleep.assert_not_called()


def oauth_client() -> Discogs:
    return Discogs(
        consumer_key="ck",
        consumer_secret="cs",
        access_token="at",
        access_token_secret="ats",
    )


def oauth_params(call: respx.models.Call) -> dict[str, str]:
    return dict(re.findall(r'(\w+)="([^"]*)"', call.request.headers["Authorization"]))


def fail_once(first):
    """Raise or return *first* for the first request, then a release."""
    responses = iter([first, respx.MockResponse(200, json=make_release())])

    def side_effect(request):
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    return side_effect


class TestRetrySigning:
    """Every network attempt carries its own OAuth nonce and timestamp."""

    @pytest.mark.parametrize(
        "first",
        [
            respx.MockResponse(503, json={"message": "Unavailable"}),
            httpx2.ConnectError("Connection refused"),
        ],
        ids=["503", "connect-error"],
    )
    def test_retry_gets_a_fresh_nonce(self, respx_mock, first):
        client = oauth_client()
        route = respx_mock.get("/releases/352665").mock(side_effect=fail_once(first))

        with patch("time.sleep"):
            client._send("GET", f"{BASE_URL}/releases/352665")

        assert route.call_count == 2
        nonces = [oauth_params(call)["oauth_nonce"] for call in route.calls]
        assert nonces[0] != nonces[1]

    def test_retry_gets_the_current_timestamp(self, respx_mock):
        client = oauth_client()
        route = respx_mock.get("/releases/352665").mock(
            side_effect=fail_once(respx.MockResponse(503))
        )
        clock = [1_700_000_000.0]

        def advance(delay):
            clock[0] += 120

        with (
            patch("time.sleep", side_effect=advance),
            patch("time.time", lambda: clock[0]),
        ):
            client._send("GET", f"{BASE_URL}/releases/352665")

        timestamps = [oauth_params(call)["oauth_timestamp"] for call in route.calls]
        assert timestamps == ["1700000000", "1700000120"]

    @pytest.mark.parametrize(
        ("make_client", "authorization"),
        [
            (lambda: Discogs(token="t"), "Discogs token=t"),
            (
                lambda: Discogs(consumer_key="ck", consumer_secret="cs"),
                "Discogs key=ck, secret=cs",
            ),
        ],
        ids=["token", "consumer"],
    )
    def test_static_credentials_are_resent_unchanged(
        self, respx_mock, make_client, authorization
    ):
        client = make_client()
        route = respx_mock.get("/releases/352665").mock(
            side_effect=fail_once(respx.MockResponse(503))
        )

        with patch("time.sleep"):
            client._send("GET", f"{BASE_URL}/releases/352665")

        assert [call.request.headers["Authorization"] for call in route.calls] == [
            authorization,
            authorization,
        ]
