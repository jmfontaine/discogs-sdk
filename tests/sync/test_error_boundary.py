"""HTTP failures must be mapped before any endpoint parses the response body."""

from __future__ import annotations

import copy
import pickle
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import patch

import httpx2
import pytest
import respx

from discogs_sdk import Discogs, RateLimit
from discogs_sdk._base_client import may_retry_transport_error
from discogs_sdk._exceptions import (
    AuthenticationError,
    DiscogsAPIError,
    DiscogsConnectionError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
)
from tests.conftest import (
    BASE_URL,
    make_artist_release,
    make_paginated_response,
    make_release,
)

RATELIMIT_HEADERS = {
    "X-Discogs-Ratelimit": "60",
    "X-Discogs-Ratelimit-Used": "14",
    "X-Discogs-Ratelimit-Remaining": "46",
}

GATEWAY_HTML = (
    "<html><head><title>502 Bad Gateway</title></head><body>nginx</body></html>"
)

# Transport failures a fresh attempt can cure, and ones that repeat on every attempt.
TRANSIENT_CAUSES = [
    httpx2.ConnectError("Connection refused"),
    httpx2.ReadTimeout("Timed out reading response"),
    httpx2.RemoteProtocolError("Server disconnected without sending a response."),
]
DETERMINISTIC_CAUSES = [
    httpx2.ProxyError("407 Proxy Authentication Required"),
    httpx2.UnsupportedProtocol("Request URL has an unsupported protocol"),
    httpx2.LocalProtocolError("Illegal header value"),
    httpx2.DecodingError("Error -3 while decompressing data"),
    httpx2.TooManyRedirects("Exceeded maximum allowed redirects."),
]


def request_error_classes(
    cls: type[httpx2.RequestError] = httpx2.RequestError,
) -> list[type[httpx2.RequestError]]:
    """*cls* and every ``httpx2`` subclass of it: each one the SDK maps."""
    found = [cls]
    for subclass in cls.__subclasses__():
        if subclass.__module__.startswith("httpx2"):
            found += request_error_classes(subclass)
    return found


@pytest.fixture
def client(respx_mock):
    return Discogs(token="test-token", max_retries=0)


class TestNonJsonFailures:
    def test_lazy_read(self, client, respx_mock):
        respx_mock.get("/releases/352665").respond(502, html=GATEWAY_HTML)

        with pytest.raises(DiscogsAPIError) as exc_info:
            _ = client.releases.get(352665).title

        assert exc_info.value.status_code == 502
        assert exc_info.value.response_body == GATEWAY_HTML

    def test_paginated_read(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/collection/folders/0/releases").respond(
            502, html=GATEWAY_HTML
        )

        with pytest.raises(DiscogsAPIError) as exc_info:
            for _ in (
                client.users.get("trent_reznor")
                .collection.folders.get(0)
                .releases.list()
            ):
                pass

        assert exc_info.value.status_code == 502

    def test_resource_method(self, client, respx_mock):
        respx_mock.post("/marketplace/orders/1-1").respond(502, html=GATEWAY_HTML)

        with pytest.raises(DiscogsAPIError) as exc_info:
            client.marketplace.orders.update("1-1", status="Shipped")

        assert exc_info.value.status_code == 502
        assert exc_info.value.method == "POST"
        assert exc_info.value.url == f"{BASE_URL}/marketplace/orders/1-1"

    def test_identity(self, client, respx_mock):
        respx_mock.get("/oauth/identity").respond(502, html=GATEWAY_HTML)

        with pytest.raises(DiscogsAPIError) as exc_info:
            client.user.identity()

        assert exc_info.value.status_code == 502

    def test_empty_401_body_keeps_specialized_error(self, client, respx_mock):
        respx_mock.get("/oauth/identity").respond(401, content=b"")

        with pytest.raises(AuthenticationError) as exc_info:
            client.user.identity()

        assert exc_info.value.response_body == ""

    def test_empty_403_body_keeps_specialized_error(self, client, respx_mock):
        respx_mock.get("/users/atticus_ross/collection/folders/1/releases").respond(
            403, content=b""
        )

        with pytest.raises(ForbiddenError) as exc_info:
            for _ in (
                client.users.get("atticus_ross")
                .collection.folders.get(1)
                .releases.list()
            ):
                pass

        assert exc_info.value.status_code == 403
        assert exc_info.value.response_body == ""

    def test_plain_text_429_keeps_retry_after(self, client, respx_mock):
        respx_mock.get("/releases/352665").respond(
            429,
            text="slow down",
            headers={"Retry-After": "17", **RATELIMIT_HEADERS},
        )

        with pytest.raises(RateLimitError) as exc_info:
            _ = client.releases.get(352665).title

        assert exc_info.value.retry_after == "17"
        assert exc_info.value.ratelimit == RateLimit(60, 14, 46)
        assert exc_info.value.response_body == "slow down"

    def test_json_error_messages_still_map(self, client, respx_mock):
        respx_mock.get("/releases/352665").respond(
            404, json={"message": "Release not found."}
        )

        with pytest.raises(NotFoundError) as exc_info:
            _ = client.releases.get(352665).title

        assert str(exc_info.value) == "404: Release not found."

    def test_oversized_html_body_bounds_message_only(self, client, respx_mock):
        page = GATEWAY_HTML.replace("nginx", "nginx " * 100)
        respx_mock.get("/releases/352665").respond(502, html=page)

        with pytest.raises(DiscogsAPIError) as exc_info:
            _ = client.releases.get(352665).title

        assert len(exc_info.value.args[0]) == 500
        assert exc_info.value.args[0].endswith("…")
        assert exc_info.value.response_body == page

    def test_oversized_429_body_keeps_retry_after(self, client, respx_mock):
        respx_mock.get("/releases/352665").respond(
            429, text="slow down " * 60, headers={"Retry-After": "17"}
        )

        with pytest.raises(RateLimitError) as exc_info:
            _ = client.releases.get(352665).title

        assert len(exc_info.value.args[0]) == 500
        assert exc_info.value.retry_after == "17"
        assert exc_info.value.response_body == "slow down " * 60


class TestNonObjectJsonFailures:
    """A JSON error body that is not an object is kept as the raw response text."""

    @pytest.mark.parametrize(
        "raw", ['["Release not found."]', '"Release not found."'], ids=["list", "str"]
    )
    @pytest.mark.parametrize(
        ("status", "error_cls"), [(404, NotFoundError), (500, DiscogsAPIError)]
    )
    def test_raw_text_becomes_the_message(
        self, client, respx_mock, raw, status, error_cls
    ):
        respx_mock.get("/releases/352665").respond(
            status, content=raw.encode(), content_type="application/json"
        )

        with pytest.raises(error_cls) as exc_info:
            _ = client.releases.get(352665).title

        assert type(exc_info.value) is error_cls
        assert exc_info.value.status_code == status
        assert exc_info.value.args[0] == raw
        assert exc_info.value.response_body == raw


class TestFailedRequestIsIdentified:
    def test_not_found_names_method_and_url(self, client, respx_mock):
        respx_mock.get("/releases/352665").respond(
            404, json={"message": "Release not found."}
        )

        with pytest.raises(NotFoundError) as exc_info:
            _ = client.releases.get(352665).title

        assert exc_info.value.method == "GET"
        assert exc_info.value.url == f"{BASE_URL}/releases/352665"

    def test_url_keeps_query_string(self, client, respx_mock):
        respx_mock.get("/database/search").respond(500, json={"message": "Boom"})

        with pytest.raises(DiscogsAPIError) as exc_info:
            for _ in client.search(q="Nine Inch Nails", type="artist"):
                pass

        assert exc_info.value.url == (
            f"{BASE_URL}/database/search?page=1&q=Nine+Inch+Nails&type=artist"
        )

    def test_failed_second_page_names_that_page(self, client, respx_mock):
        page1 = make_paginated_response(
            "releases",
            [make_artist_release()],
            pages=2,
            next_url=f"{BASE_URL}/artists/3857/releases?page=2&per_page=1",
        )
        respx_mock.get("/artists/3857/releases").mock(
            side_effect=[
                respx.MockResponse(200, json=page1),
                respx.MockResponse(404, json={"message": "Page not found."}),
            ]
        )

        with pytest.raises(NotFoundError) as exc_info:
            for _ in client.artists.get(3857).releases.list():
                pass

        assert exc_info.value.url == (
            f"{BASE_URL}/artists/3857/releases?page=2&per_page=1"
        )

    def test_exhausted_retries_keep_the_rate_limit_budget(self, respx_mock):
        client = Discogs(token="test-token", max_retries=1)
        route = respx_mock.get("/releases/352665").respond(
            500, json={"message": "Boom"}, headers=RATELIMIT_HEADERS
        )

        with patch("time.sleep"), pytest.raises(DiscogsAPIError) as exc_info:
            _ = client.releases.get(352665).title

        assert route.call_count == 2
        assert exc_info.value.method == "GET"
        assert exc_info.value.ratelimit == RateLimit(60, 14, 46)

    def test_ratelimit_is_none_without_the_headers(self, client, respx_mock):
        respx_mock.get("/releases/352665").respond(500, json={"message": "Boom"})

        with pytest.raises(DiscogsAPIError) as exc_info:
            _ = client.releases.get(352665).title

        assert exc_info.value.ratelimit is None


class TestSuccessfulResponsesAreUntouched:
    def test_204_mutation(self, client, respx_mock):
        route = respx_mock.delete("/marketplace/listings/1").respond(204)

        client.marketplace.listings.delete(1)

        assert route.call_count == 1

    def test_binary_download_preserves_bytes(self, client, respx_mock):
        csv = b"release_id,price\n352665,29.99\n"
        respx_mock.get("/inventory/export/1/download").respond(200, content=csv)

        assert client.exports.download(1) == csv

    def test_paginated_success(self, client, respx_mock):
        body = make_paginated_response("releases", [make_release()])
        respx_mock.get("/users/trent_reznor/collection/folders/0/releases").respond(
            200, json=body
        )

        items = [
            item
            for item in client.users.get("trent_reznor")
            .collection.folders.get(0)
            .releases.list()
        ]

        assert len(items) == 1

    def test_malformed_success_body_is_not_replaced_by_a_fallback(
        self, client, respx_mock
    ):
        respx_mock.get("/releases/352665").respond(200, text="not json")

        with pytest.raises(ValueError):
            _ = client.releases.get(352665).title


class TestHttpValidationErrorIsDistinctFromModelValidation:
    def test_422_raises_sdk_validation_error(self, client, respx_mock):
        from discogs_sdk._exceptions import ValidationError as SDKValidationError

        respx_mock.post("/marketplace/orders/1-1").respond(
            422, json={"message": "Invalid status"}
        )

        with pytest.raises(SDKValidationError) as exc_info:
            client.marketplace.orders.update("1-1", status="Nope")

        assert exc_info.value.status_code == 422


def cause_id(cause: httpx2.RequestError) -> str:
    return type(cause).__name__


def read_release(client: Discogs) -> None:
    _ = client.releases.get(352665).title


def create_listing(client: Discogs) -> None:
    client.marketplace.listings.create(
        release_id=352665, condition="Mint (M)", price=29.99
    )


# (HTTP method, path, call): a read the SDK retries, and a write it never replays.
REQUESTS = [
    pytest.param("GET", "/releases/352665", read_release, id="read"),
    pytest.param("POST", "/marketplace/listings", create_listing, id="write"),
]


class TestConnectionErrorTransience:
    """``transient`` says whether a read failing the same way would be retried."""

    @pytest.mark.parametrize("cause", TRANSIENT_CAUSES, ids=cause_id)
    def test_transient_causes(self, client, respx_mock, cause):
        respx_mock.get("/releases/352665").mock(side_effect=cause)

        with pytest.raises(DiscogsConnectionError) as exc_info:
            _ = client.releases.get(352665).title

        assert exc_info.value.transient is True
        assert exc_info.value.__cause__ is cause

    @pytest.mark.parametrize("cause", DETERMINISTIC_CAUSES, ids=cause_id)
    def test_deterministic_causes(self, client, respx_mock, cause):
        respx_mock.get("/releases/352665").mock(side_effect=cause)

        with pytest.raises(DiscogsConnectionError) as exc_info:
            _ = client.releases.get(352665).title

        assert exc_info.value.transient is False
        assert exc_info.value.__cause__ is cause

    @pytest.mark.parametrize(
        "cause_cls", request_error_classes(), ids=lambda cls: cls.__name__
    )
    @pytest.mark.parametrize(("method", "path", "call"), REQUESTS)
    def test_matches_the_read_retry_policy(
        self, client, respx_mock, method, path, call, cause_cls
    ):
        cause = cause_cls("Transport failure")
        respx_mock.route(method=method, path=path).mock(side_effect=cause)

        with pytest.raises(DiscogsConnectionError) as exc_info:
            call(client)

        assert exc_info.value.__cause__ is cause
        assert exc_info.value.transient is may_retry_transport_error("GET", cause)

    @pytest.mark.parametrize(
        "round_trip",
        [lambda exc: pickle.loads(pickle.dumps(exc)), copy.copy, copy.deepcopy],
        ids=["pickle", "copy", "deepcopy"],
    )
    @pytest.mark.parametrize(
        ("cause", "transient"),
        [(TRANSIENT_CAUSES[0], True), (DETERMINISTIC_CAUSES[0], False)],
        ids=["transient", "deterministic"],
    )
    def test_survives_pickle_and_copy(
        self, client, respx_mock, round_trip, cause, transient
    ):
        respx_mock.get("/releases/352665").mock(side_effect=cause)

        with pytest.raises(DiscogsConnectionError) as exc_info:
            _ = client.releases.get(352665).title
        clone = round_trip(exc_info.value)

        assert type(clone) is DiscogsConnectionError
        assert clone.transient is transient
        assert clone.args == exc_info.value.args


class TestRateLimitErrorRetryAfterSeconds:
    """``retry_after_seconds`` is the parsed delay; ``retry_after`` stays raw."""

    @pytest.mark.parametrize(
        ("header", "seconds"),
        [
            pytest.param("30", 30.0, id="whole"),
            pytest.param("1.5", 1.5, id="decimal"),
            pytest.param("0", 0.0, id="zero"),
            pytest.param("soon", None, id="invalid"),
            pytest.param("-5", None, id="negative"),
        ],
    )
    def test_header_value(self, client, respx_mock, header, seconds):
        respx_mock.get("/releases/352665").respond(
            429, json={"message": "slow down"}, headers={"Retry-After": header}
        )

        with pytest.raises(RateLimitError) as exc_info:
            _ = client.releases.get(352665).title

        assert exc_info.value.retry_after == header
        if seconds is None:
            assert exc_info.value.retry_after_seconds is None
        else:
            assert type(exc_info.value.retry_after_seconds) is float
            assert exc_info.value.retry_after_seconds == seconds

    def test_missing_header(self, client, respx_mock):
        respx_mock.get("/releases/352665").respond(429, json={"message": "slow down"})

        with pytest.raises(RateLimitError) as exc_info:
            _ = client.releases.get(352665).title

        assert exc_info.value.retry_after is None
        assert exc_info.value.retry_after_seconds is None

    def test_future_http_date(self, client, respx_mock):
        when = datetime.now(timezone.utc) + timedelta(seconds=30)
        header = format_datetime(when, usegmt=True)
        respx_mock.get("/releases/352665").respond(
            429, json={"message": "slow down"}, headers={"Retry-After": header}
        )

        with pytest.raises(RateLimitError) as exc_info:
            _ = client.releases.get(352665).title

        assert exc_info.value.retry_after == header
        seconds = exc_info.value.retry_after_seconds
        assert seconds is not None
        assert 28.0 < seconds <= 30.0  # the header has whole-second resolution

    def test_past_http_date_is_zero(self, client, respx_mock):
        header = "Wed, 21 Oct 2015 07:28:00 GMT"
        respx_mock.get("/releases/352665").respond(
            429, json={"message": "slow down"}, headers={"Retry-After": header}
        )

        with pytest.raises(RateLimitError) as exc_info:
            _ = client.releases.get(352665).title

        assert exc_info.value.retry_after == header
        assert exc_info.value.retry_after_seconds == 0.0
