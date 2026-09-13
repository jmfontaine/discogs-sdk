from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any

from discogs_sdk._async._lazy import AsyncLazyResource
from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk.models._common import Condition, CurrencyCode
from discogs_sdk.models.marketplace import Fee, Listing, Order, OrderMessage

if TYPE_CHECKING:
    from discogs_sdk._async._client import AsyncDiscogs


class OrderMessages(AsyncAPIResource):
    def __init__(self, client, order_id: str) -> None:
        super().__init__(client)
        self._order_id = order_id

    def list(
        self,
        *,
        page: int | None = None,
        per_page: int | None = None,
    ) -> AsyncPage[OrderMessage]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return AsyncPage(
            client=self._client,
            items_key="messages",
            model_cls=OrderMessage,
            params=params,
            path=f"/marketplace/orders/{self._order_id}/messages",
        )

    async def create(self, *, message: str | None = None, status: str | None = None) -> OrderMessage:
        body = {k: v for k, v in {"message": message, "status": status}.items() if v is not None}
        response = await self._post(
            f"/marketplace/orders/{self._order_id}/messages",
            json=body,
        )
        return self._parse_response(response, OrderMessage)


class OrderProxy(AsyncLazyResource[Order]):
    """Lazy ``Order`` with its typed sub-resources."""

    _order_id: str

    def __init__(self, client: AsyncDiscogs, order_id: str) -> None:
        super().__init__(client, f"/marketplace/orders/{order_id}", Order)
        self._order_id = order_id

    @cached_property
    def messages(self) -> OrderMessages:
        return OrderMessages(self._client, self._order_id)


class MarketplaceOrders(AsyncAPIResource):
    def get(self, order_id: str) -> OrderProxy:
        return OrderProxy(self._client, order_id)

    def list(
        self,
        *,
        status: str | None = None,
        sort: str | None = None,
        sort_order: str | None = None,
        page: int | None = None,
        per_page: int | None = None,
    ) -> AsyncPage[Order]:
        params = {
            k: v
            for k, v in {
                "status": status,
                "sort": sort,
                "sort_order": sort_order,
                "page": page,
                "per_page": per_page,
            }.items()
            if v
        }
        return AsyncPage(
            client=self._client,
            items_key="orders",
            model_cls=Order,
            params=params,
            path="/marketplace/orders",
        )

    async def update(self, order_id: str, **kwargs: Any) -> Order:
        response = await self._post(f"/marketplace/orders/{order_id}", json=kwargs)
        return self._parse_response(response, Order)


class ListingProxy(AsyncLazyResource[Listing]):
    """Lazy marketplace listing."""


class MarketplaceListings(AsyncAPIResource):
    def get(self, listing_id: int) -> ListingProxy:
        return ListingProxy(self._client, f"/marketplace/listings/{listing_id}", Listing)

    async def create(
        self, *, release_id: int, condition: Condition, price: float, status: str = "For Sale", **kwargs: Any
    ) -> Listing:
        body = {"release_id": release_id, "condition": condition, "price": price, "status": status, **kwargs}
        response = await self._post("/marketplace/listings", json=body)
        return self._parse_response(response, Listing)

    async def update(self, listing_id: int, **kwargs: Any) -> None:
        await self._post(f"/marketplace/listings/{listing_id}", json=kwargs)

    async def delete(self, listing_id: int) -> None:
        await self._delete(f"/marketplace/listings/{listing_id}")


class FeeProxy(AsyncLazyResource[Fee]):
    """Lazy marketplace fee quote."""


class MarketplaceFee(AsyncAPIResource):
    def get(self, *, price: float, currency: CurrencyCode | None = None) -> FeeProxy:
        if currency:
            path = f"/marketplace/fee/{price}/{currency}"
        else:
            path = f"/marketplace/fee/{price}"
        return FeeProxy(self._client, path, Fee)


class Marketplace:
    def __init__(self, client: AsyncDiscogs) -> None:
        self._client = client

    @cached_property
    def fee(self) -> MarketplaceFee:
        return MarketplaceFee(self._client)

    @cached_property
    def listings(self) -> MarketplaceListings:
        return MarketplaceListings(self._client)

    @cached_property
    def orders(self) -> MarketplaceOrders:
        return MarketplaceOrders(self._client)
