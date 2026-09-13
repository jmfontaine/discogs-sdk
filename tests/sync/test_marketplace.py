"""Tests for sync Marketplace resource."""

from __future__ import annotations

import pytest
import respx

from discogs_sdk._exceptions import NotFoundError
from discogs_sdk.models.marketplace import Listing, Order, OrderMessage
from tests.conftest import (
    BASE_URL,
    make_fee,
    make_listing,
    make_listing_created,
    make_order,
    make_order_message,
    make_paginated_response,
)


class TestMarketplaceListings:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.marketplace.listings.get(123)
        assert respx_mock.calls.call_count == 0

    def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/marketplace/listings/123").mock(return_value=respx.MockResponse(200, json=make_listing()))
        lazy = client.marketplace.listings.get(123)
        assert lazy.id == 123

    def test_create_returns_the_acknowledged_identifier(self, client, respx_mock):
        route = respx_mock.post("/marketplace/listings").mock(
            return_value=respx.MockResponse(201, json=make_listing_created())
        )
        result = client.marketplace.listings.create(release_id=400027, condition="Mint (M)", price=9.99)

        assert isinstance(result, Listing)
        assert result.id == 41578241
        assert result.resource_url == f"{BASE_URL}/marketplace/listings/41578241"
        assert route.call_count == 1
        # No hidden follow-up fetch to flesh out the listing.
        assert [call.request.method for call in respx_mock.calls] == ["POST"]

    def test_update(self, client, respx_mock):
        respx_mock.post("/marketplace/listings/123").mock(return_value=respx.MockResponse(204))
        client.marketplace.listings.update(123, price=12.99)

    def test_update_error(self, client, respx_mock):
        respx_mock.post("/marketplace/listings/123").mock(
            return_value=respx.MockResponse(404, json={"message": "Not Found"})
        )
        with pytest.raises(NotFoundError):
            client.marketplace.listings.update(123, price=12.99)

    def test_delete(self, client, respx_mock):
        respx_mock.delete("/marketplace/listings/123").mock(return_value=respx.MockResponse(204))
        client.marketplace.listings.delete(123)

    def test_delete_error(self, client, respx_mock):
        respx_mock.delete("/marketplace/listings/999").mock(
            return_value=respx.MockResponse(404, json={"message": "Not Found"})
        )
        with pytest.raises(NotFoundError):
            client.marketplace.listings.delete(999)


class TestMarketplaceOrders:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.marketplace.orders.get("1-1")
        assert respx_mock.calls.call_count == 0

    def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/marketplace/orders/1-1").mock(return_value=respx.MockResponse(200, json=make_order()))
        lazy = client.marketplace.orders.get("1-1")
        assert lazy.id == "1-1"

    def test_list_orders(self, client, respx_mock):
        respx_mock.get("/marketplace/orders").mock(
            return_value=respx.MockResponse(200, json=make_paginated_response("orders", [make_order()]))
        )
        results = list(client.marketplace.orders.list())
        assert len(results) == 1
        assert isinstance(results[0], Order)

    def test_update_order(self, client, respx_mock):
        respx_mock.post("/marketplace/orders/1-1").mock(
            return_value=respx.MockResponse(200, json=make_order(status="Shipped"))
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
            return_value=respx.MockResponse(200, json=make_paginated_response("messages", [make_order_message()]))
        )
        lazy = client.marketplace.orders.get("1-1")
        results = list(lazy.messages.list())
        assert len(results) == 1
        assert isinstance(results[0], OrderMessage)

    def test_create_message(self, client, respx_mock):
        respx_mock.post("/marketplace/orders/1-1/messages").mock(
            return_value=respx.MockResponse(200, json=make_order_message(message="Shipped!"))
        )
        lazy = client.marketplace.orders.get("1-1")
        result = lazy.messages.create(message="Shipped!")
        assert result.message == "Shipped!"

    def test_create_message_with_status(self, client, respx_mock):
        respx_mock.post("/marketplace/orders/1-1/messages").mock(
            return_value=respx.MockResponse(200, json=make_order_message(message="Shipped!"))
        )
        lazy = client.marketplace.orders.get("1-1")
        result = lazy.messages.create(message="Shipped!", status="Shipped")
        assert isinstance(result, OrderMessage)


class TestMarketplaceFee:
    def test_fee_without_currency(self, client, respx_mock):
        respx_mock.get("/marketplace/fee/10.0").mock(return_value=respx.MockResponse(200, json=make_fee()))
        lazy = client.marketplace.fee.get(price=10.0)
        assert lazy.value == 0.99

    def test_fee_with_currency(self, client, respx_mock):
        respx_mock.get("/marketplace/fee/10.0/EUR").mock(
            return_value=respx.MockResponse(200, json=make_fee(currency="EUR"))
        )
        lazy = client.marketplace.fee.get(price=10.0, currency="EUR")
        assert lazy.currency == "EUR"


class TestListingCurrencySelection:
    def test_currency_does_not_fetch_eagerly(self, client, respx_mock):
        _proxy = client.marketplace.listings.get(123, curr_abbr="EUR")
        assert respx_mock.calls.call_count == 0

    def test_listing_sends_requested_currency(self, client, respx_mock):
        route = respx_mock.get("/marketplace/listings/123").mock(
            return_value=respx.MockResponse(200, json=make_listing())
        )
        _ = client.marketplace.listings.get(123, curr_abbr="EUR").id
        assert route.calls[0].request.url.params["curr_abbr"] == "EUR"

    def test_listing_without_currency_sends_no_parameter(self, client, respx_mock):
        route = respx_mock.get("/marketplace/listings/123").mock(
            return_value=respx.MockResponse(200, json=make_listing())
        )
        _ = client.marketplace.listings.get(123).id
        assert "curr_abbr" not in route.calls[0].request.url.params


class TestOrderFilters:
    def test_date_range_is_sent_as_supplied(self, client, respx_mock):
        route = respx_mock.get("/marketplace/orders").mock(
            return_value=respx.MockResponse(200, json=make_paginated_response("orders", [make_order()]))
        )

        page = client.marketplace.orders.list(
            created_after="2019-06-24T20:58:58Z",
            created_before="2020-06-24T20:58:58Z",
        )
        _ = list(page)

        params = route.calls[0].request.url.params
        assert params["created_after"] == "2019-06-24T20:58:58Z"
        assert params["created_before"] == "2020-06-24T20:58:58Z"

    @pytest.mark.parametrize(("archived", "expected"), [(True, "true"), (False, "false")])
    def test_both_archive_states_reach_the_api(self, client, respx_mock, archived, expected):
        route = respx_mock.get("/marketplace/orders").mock(
            return_value=respx.MockResponse(200, json=make_paginated_response("orders", [make_order()]))
        )

        _ = list(client.marketplace.orders.list(archived=archived))

        assert route.calls[0].request.url.params["archived"] == expected

    def test_omitting_archived_sends_no_parameter(self, client, respx_mock):
        route = respx_mock.get("/marketplace/orders").mock(
            return_value=respx.MockResponse(200, json=make_paginated_response("orders", [make_order()]))
        )

        _ = list(client.marketplace.orders.list())

        assert "archived" not in route.calls[0].request.url.params
