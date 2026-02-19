"""Tests for sync Marketplace resource."""

from __future__ import annotations

import httpx
import pytest

from discogs_sdk._exceptions import NotFoundError
from discogs_sdk.models.marketplace import Listing, Order, OrderMessage

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

    def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/marketplace/listings/123").mock(return_value=httpx.Response(200, json=make_listing()))
        lazy = client.marketplace.listings.get(123)
        assert lazy.id == 123

    def test_create(self, client, respx_mock):
        respx_mock.post("/marketplace/listings").mock(return_value=httpx.Response(201, json=make_listing()))
        result = client.marketplace.listings.create(release_id=400027, condition="Mint (M)", price=9.99)
        assert isinstance(result, Listing)

    def test_update(self, client, respx_mock):
        respx_mock.post("/marketplace/listings/123").mock(return_value=httpx.Response(204))
        client.marketplace.listings.update(123, price=12.99)

    def test_update_error(self, client, respx_mock):
        respx_mock.post("/marketplace/listings/123").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        with pytest.raises(NotFoundError):
            client.marketplace.listings.update(123, price=12.99)

    def test_delete(self, client, respx_mock):
        respx_mock.delete("/marketplace/listings/123").mock(return_value=httpx.Response(204))
        client.marketplace.listings.delete(123)

    def test_delete_error(self, client, respx_mock):
        respx_mock.delete("/marketplace/listings/999").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        with pytest.raises(NotFoundError):
            client.marketplace.listings.delete(999)


class TestMarketplaceOrders:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.marketplace.orders.get("1-1")
        assert respx_mock.calls.call_count == 0

    def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/marketplace/orders/1-1").mock(return_value=httpx.Response(200, json=make_order()))
        lazy = client.marketplace.orders.get("1-1")
        assert lazy.id == "1-1"

    def test_list_orders(self, client, respx_mock):
        respx_mock.get("/marketplace/orders").mock(
            return_value=httpx.Response(200, json=make_paginated_response("orders", [make_order()]))
        )
        results = list(client.marketplace.orders.list())
        assert len(results) == 1
        assert isinstance(results[0], Order)

    def test_update_order(self, client, respx_mock):
        respx_mock.post("/marketplace/orders/1-1").mock(
            return_value=httpx.Response(200, json=make_order(status="Shipped"))
        )
        result = client.marketplace.orders.update("1-1", status="Shipped")
        assert result.status == "Shipped"


class TestOrderMessages:
    def test_messages_accessible_without_http(self, client, respx_mock):
        lazy = client.marketplace.orders.get("1-1")
        _ = lazy.messages
        assert respx_mock.calls.call_count == 0

    def test_list_messages(self, client, respx_mock):
        respx_mock.get("/marketplace/orders/1-1/messages").mock(
            return_value=httpx.Response(200, json=make_paginated_response("messages", [make_order_message()]))
        )
        lazy = client.marketplace.orders.get("1-1")
        results = list(lazy.messages.list())
        assert len(results) == 1
        assert isinstance(results[0], OrderMessage)

    def test_create_message(self, client, respx_mock):
        respx_mock.post("/marketplace/orders/1-1/messages").mock(
            return_value=httpx.Response(200, json=make_order_message(message="Shipped!"))
        )
        lazy = client.marketplace.orders.get("1-1")
        result = lazy.messages.create(message="Shipped!")
        assert result.message == "Shipped!"

    def test_create_message_with_status(self, client, respx_mock):
        respx_mock.post("/marketplace/orders/1-1/messages").mock(
            return_value=httpx.Response(200, json=make_order_message(message="Shipped!"))
        )
        lazy = client.marketplace.orders.get("1-1")
        result = lazy.messages.create(message="Shipped!", status="Shipped")
        assert isinstance(result, OrderMessage)


class TestMarketplaceFee:
    def test_fee_without_currency(self, client, respx_mock):
        respx_mock.get("/marketplace/fee/10.0").mock(return_value=httpx.Response(200, json=make_fee()))
        lazy = client.marketplace.fee.get(price=10.0)
        assert lazy.value == 0.99

    def test_fee_with_currency(self, client, respx_mock):
        respx_mock.get("/marketplace/fee/10.0/EUR").mock(
            return_value=httpx.Response(200, json=make_fee(currency="EUR"))
        )
        lazy = client.marketplace.fee.get(price=10.0, currency="EUR")
        assert lazy.currency == "EUR"
