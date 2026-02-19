"""Tests for async Marketplace resource."""

from __future__ import annotations

import httpx
import pytest

from discogs_sdk._exceptions import NotFoundError
from discogs_sdk.models.marketplace import Fee, Listing, Order, OrderMessage

from tests.conftest import (
    make_fee,
    make_listing,
    make_order,
    make_order_message,
    make_paginated_response,
)


class TestMarketplaceListings:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.marketplace.listings.get(123)
        assert respx_mock.calls.call_count == 0

    async def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/marketplace/listings/123").mock(return_value=httpx.Response(200, json=make_listing()))
        result = await client.marketplace.listings.get(123)
        assert isinstance(result, Listing)
        assert result.id == 123

    async def test_create(self, client, respx_mock):
        respx_mock.post("/marketplace/listings").mock(return_value=httpx.Response(201, json=make_listing()))
        result = await client.marketplace.listings.create(release_id=400027, condition="Mint (M)", price=9.99)
        assert isinstance(result, Listing)

    async def test_update(self, client, respx_mock):
        respx_mock.post("/marketplace/listings/123").mock(return_value=httpx.Response(204))
        await client.marketplace.listings.update(123, price=12.99)

    async def test_update_error(self, client, respx_mock):
        respx_mock.post("/marketplace/listings/123").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        with pytest.raises(NotFoundError):
            await client.marketplace.listings.update(123, price=12.99)

    async def test_delete(self, client, respx_mock):
        respx_mock.delete("/marketplace/listings/123").mock(return_value=httpx.Response(204))
        await client.marketplace.listings.delete(123)

    async def test_delete_error_empty_body(self, client, respx_mock):
        respx_mock.delete("/marketplace/listings/999").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        with pytest.raises(NotFoundError):
            await client.marketplace.listings.delete(999)


class TestMarketplaceOrders:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.marketplace.orders.get("1-1")
        assert respx_mock.calls.call_count == 0

    async def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/marketplace/orders/1-1").mock(return_value=httpx.Response(200, json=make_order()))
        result = await client.marketplace.orders.get("1-1")
        assert isinstance(result, Order)
        assert result.id == "1-1"

    async def test_list_orders(self, client, respx_mock):
        respx_mock.get("/marketplace/orders").mock(
            return_value=httpx.Response(200, json=make_paginated_response("orders", [make_order()]))
        )
        results = [item async for item in client.marketplace.orders.list()]
        assert len(results) == 1
        assert isinstance(results[0], Order)

    async def test_list_with_params(self, client, respx_mock):
        respx_mock.get("/marketplace/orders").mock(
            return_value=httpx.Response(200, json=make_paginated_response("orders", [make_order()]))
        )
        results = [
            item async for item in client.marketplace.orders.list(status="New Order", sort="id", sort_order="desc")
        ]
        assert len(results) == 1

    async def test_update_order(self, client, respx_mock):
        respx_mock.post("/marketplace/orders/1-1").mock(
            return_value=httpx.Response(200, json=make_order(status="Shipped"))
        )
        result = await client.marketplace.orders.update("1-1", status="Shipped")
        assert isinstance(result, Order)
        assert result.status == "Shipped"


class TestOrderMessages:
    def test_messages_accessible_without_http(self, client, respx_mock):
        lazy = client.marketplace.orders.get("1-1")
        _ = lazy.messages
        assert respx_mock.calls.call_count == 0

    async def test_list_messages(self, client, respx_mock):
        respx_mock.get("/marketplace/orders/1-1/messages").mock(
            return_value=httpx.Response(200, json=make_paginated_response("messages", [make_order_message()]))
        )
        lazy = client.marketplace.orders.get("1-1")
        results = [item async for item in lazy.messages.list()]
        assert len(results) == 1
        assert isinstance(results[0], OrderMessage)

    async def test_create_message(self, client, respx_mock):
        respx_mock.post("/marketplace/orders/1-1/messages").mock(
            return_value=httpx.Response(200, json=make_order_message(message="Shipped!"))
        )
        lazy = client.marketplace.orders.get("1-1")
        result = await lazy.messages.create(message="Shipped!", status="Shipped")
        assert isinstance(result, OrderMessage)
        assert result.message == "Shipped!"


class TestMarketplaceFee:
    async def test_fee_without_currency(self, client, respx_mock):
        respx_mock.get("/marketplace/fee/10.0").mock(return_value=httpx.Response(200, json=make_fee()))
        result = await client.marketplace.fee.get(price=10.0)
        assert isinstance(result, Fee)
        assert result.value == 0.99

    async def test_fee_with_currency(self, client, respx_mock):
        respx_mock.get("/marketplace/fee/10.0/EUR").mock(
            return_value=httpx.Response(200, json=make_fee(currency="EUR"))
        )
        result = await client.marketplace.fee.get(price=10.0, currency="EUR")
        assert isinstance(result, Fee)
        assert result.currency == "EUR"


class TestListingModel:
    async def test_required_fields(self, client, respx_mock):
        respx_mock.get("/marketplace/listings/1").mock(return_value=httpx.Response(200, json={"id": 1}))
        result = await client.marketplace.listings.get(1)
        assert result.status is None

    async def test_extra_allow(self, client, respx_mock):
        respx_mock.get("/marketplace/listings/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "_unknown_extra_field": "test"})
        )
        result = await client.marketplace.listings.get(1)
        assert result.model_extra["_unknown_extra_field"] == "test"
