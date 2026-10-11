"""HTTP failures must be mapped before any endpoint parses the response body."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import respx

from discogs_sdk import AsyncDiscogs, RateLimit
from discogs_sdk._exceptions import (
    AuthenticationError,
    DiscogsAPIError,
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


@pytest.fixture
def client(respx_mock):
    return AsyncDiscogs(token="test-token", max_retries=0)


class TestNonJsonFailures:
    async def test_lazy_read(self, client, respx_mock):
        respx_mock.get("/releases/352665").respond(502, html=GATEWAY_HTML)

        with pytest.raises(DiscogsAPIError) as exc_info:
            await client.releases.get(352665)

        assert exc_info.value.status_code == 502
        assert exc_info.value.response_body == GATEWAY_HTML

    async def test_paginated_read(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/collection/folders/0/releases").respond(
            502, html=GATEWAY_HTML
        )

        with pytest.raises(DiscogsAPIError) as exc_info:
            async for _ in (
                client.users.get("trent_reznor")
                .collection.folders.get(0)
                .releases.list()
            ):
                pass

        assert exc_info.value.status_code == 502

    async def test_resource_method(self, client, respx_mock):
        respx_mock.post("/marketplace/orders/1-1").respond(502, html=GATEWAY_HTML)

        with pytest.raises(DiscogsAPIError) as exc_info:
            await client.marketplace.orders.update("1-1", status="Shipped")

        assert exc_info.value.status_code == 502
        assert exc_info.value.method == "POST"
        assert exc_info.value.url == f"{BASE_URL}/marketplace/orders/1-1"

    async def test_identity(self, client, respx_mock):
        respx_mock.get("/oauth/identity").respond(502, html=GATEWAY_HTML)

        with pytest.raises(DiscogsAPIError) as exc_info:
            await client.user.identity()

        assert exc_info.value.status_code == 502

    async def test_empty_401_body_keeps_specialized_error(self, client, respx_mock):
        respx_mock.get("/oauth/identity").respond(401, content=b"")

        with pytest.raises(AuthenticationError) as exc_info:
            await client.user.identity()

        assert exc_info.value.response_body == ""

    async def test_empty_403_body_keeps_specialized_error(self, client, respx_mock):
        respx_mock.get("/users/atticus_ross/collection/folders/1/releases").respond(
            403, content=b""
        )

        with pytest.raises(ForbiddenError) as exc_info:
            async for _ in (
                client.users.get("atticus_ross")
                .collection.folders.get(1)
                .releases.list()
            ):
                pass

        assert exc_info.value.status_code == 403
        assert exc_info.value.response_body == ""

    async def test_plain_text_429_keeps_retry_after(self, client, respx_mock):
        respx_mock.get("/releases/352665").respond(
            429,
            text="slow down",
            headers={"Retry-After": "17", **RATELIMIT_HEADERS},
        )

        with pytest.raises(RateLimitError) as exc_info:
            await client.releases.get(352665)

        assert exc_info.value.retry_after == "17"
        assert exc_info.value.ratelimit == RateLimit(60, 14, 46)
        assert exc_info.value.response_body == "slow down"

    async def test_json_error_messages_still_map(self, client, respx_mock):
        respx_mock.get("/releases/352665").respond(
            404, json={"message": "Release not found."}
        )

        with pytest.raises(NotFoundError) as exc_info:
            await client.releases.get(352665)

        assert str(exc_info.value) == "404: Release not found."

    async def test_oversized_html_body_bounds_message_only(self, client, respx_mock):
        page = GATEWAY_HTML.replace("nginx", "nginx " * 100)
        respx_mock.get("/releases/352665").respond(502, html=page)

        with pytest.raises(DiscogsAPIError) as exc_info:
            await client.releases.get(352665)

        assert len(exc_info.value.args[0]) == 500
        assert exc_info.value.args[0].endswith("…")
        assert exc_info.value.response_body == page

    async def test_oversized_429_body_keeps_retry_after(self, client, respx_mock):
        respx_mock.get("/releases/352665").respond(
            429, text="slow down " * 60, headers={"Retry-After": "17"}
        )

        with pytest.raises(RateLimitError) as exc_info:
            await client.releases.get(352665)

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
    async def test_raw_text_becomes_the_message(
        self, client, respx_mock, raw, status, error_cls
    ):
        respx_mock.get("/releases/352665").respond(
            status, content=raw.encode(), content_type="application/json"
        )

        with pytest.raises(error_cls) as exc_info:
            await client.releases.get(352665)

        assert type(exc_info.value) is error_cls
        assert exc_info.value.status_code == status
        assert exc_info.value.args[0] == raw
        assert exc_info.value.response_body == raw


class TestFailedRequestIsIdentified:
    async def test_not_found_names_method_and_url(self, client, respx_mock):
        respx_mock.get("/releases/352665").respond(
            404, json={"message": "Release not found."}
        )

        with pytest.raises(NotFoundError) as exc_info:
            await client.releases.get(352665)

        assert exc_info.value.method == "GET"
        assert exc_info.value.url == f"{BASE_URL}/releases/352665"

    async def test_url_keeps_query_string(self, client, respx_mock):
        respx_mock.get("/database/search").respond(500, json={"message": "Boom"})

        with pytest.raises(DiscogsAPIError) as exc_info:
            async for _ in client.search(q="Nine Inch Nails", type="artist"):
                pass

        assert exc_info.value.url == (
            f"{BASE_URL}/database/search?page=1&q=Nine+Inch+Nails&type=artist"
        )

    async def test_failed_second_page_names_that_page(self, client, respx_mock):
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
            async for _ in client.artists.get(3857).releases.list():
                pass

        assert exc_info.value.url == (
            f"{BASE_URL}/artists/3857/releases?page=2&per_page=1"
        )

    async def test_exhausted_retries_keep_the_rate_limit_budget(self, respx_mock):
        client = AsyncDiscogs(token="test-token", max_retries=1)
        route = respx_mock.get("/releases/352665").respond(
            500, json={"message": "Boom"}, headers=RATELIMIT_HEADERS
        )

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(DiscogsAPIError) as exc_info,
        ):
            await client.releases.get(352665)

        assert route.call_count == 2
        assert exc_info.value.method == "GET"
        assert exc_info.value.ratelimit == RateLimit(60, 14, 46)

    async def test_ratelimit_is_none_without_the_headers(self, client, respx_mock):
        respx_mock.get("/releases/352665").respond(500, json={"message": "Boom"})

        with pytest.raises(DiscogsAPIError) as exc_info:
            await client.releases.get(352665)

        assert exc_info.value.ratelimit is None


class TestSuccessfulResponsesAreUntouched:
    async def test_204_mutation(self, client, respx_mock):
        route = respx_mock.delete("/marketplace/listings/1").respond(204)

        await client.marketplace.listings.delete(1)

        assert route.call_count == 1

    async def test_binary_download_preserves_bytes(self, client, respx_mock):
        csv = b"release_id,price\n352665,29.99\n"
        respx_mock.get("/inventory/export/1/download").respond(200, content=csv)

        assert await client.exports.download(1) == csv

    async def test_paginated_success(self, client, respx_mock):
        body = make_paginated_response("releases", [make_release()])
        respx_mock.get("/users/trent_reznor/collection/folders/0/releases").respond(
            200, json=body
        )

        items = [
            item
            async for item in client.users.get("trent_reznor")
            .collection.folders.get(0)
            .releases.list()
        ]

        assert len(items) == 1

    async def test_malformed_success_body_is_not_replaced_by_a_fallback(
        self, client, respx_mock
    ):
        respx_mock.get("/releases/352665").respond(200, text="not json")

        with pytest.raises(ValueError):
            await client.releases.get(352665)


class TestHttpValidationErrorIsDistinctFromModelValidation:
    async def test_422_raises_sdk_validation_error(self, client, respx_mock):
        from discogs_sdk._exceptions import ValidationError as SDKValidationError

        respx_mock.post("/marketplace/orders/1-1").respond(
            422, json={"message": "Invalid status"}
        )

        with pytest.raises(SDKValidationError) as exc_info:
            await client.marketplace.orders.update("1-1", status="Nope")

        assert exc_info.value.status_code == 422
