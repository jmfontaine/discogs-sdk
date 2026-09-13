"""HTTP failures must be mapped before any endpoint parses the response body."""

from __future__ import annotations

import pytest
import respx

from discogs_sdk import AsyncDiscogs
from discogs_sdk._exceptions import (
    AuthenticationError,
    DiscogsAPIError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
)
from tests.conftest import BASE_URL, make_paginated_response, make_release

GATEWAY_HTML = (
    "<html><head><title>502 Bad Gateway</title></head><body>nginx</body></html>"
)


@pytest.fixture
def respx_mock():
    with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
        yield router


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
            429, text="slow down", headers={"Retry-After": "17"}
        )

        with pytest.raises(RateLimitError) as exc_info:
            await client.releases.get(352665)

        assert exc_info.value.retry_after == "17"
        assert exc_info.value.response_body == "slow down"

    async def test_json_error_messages_still_map(self, client, respx_mock):
        respx_mock.get("/releases/352665").respond(
            404, json={"message": "Release not found."}
        )

        with pytest.raises(NotFoundError) as exc_info:
            await client.releases.get(352665)

        assert str(exc_info.value) == "404: Release not found."


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
