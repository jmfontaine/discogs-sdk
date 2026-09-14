"""Conditionally returned fields read as ``None``, not ``AttributeError``.

Several documented fields appear only for some callers or some message kinds:
a listing's ``weight`` and ``location`` only for its owner, ``in_cart`` only for
an authenticated user, ``email`` only for the profile's own user, ``tracking``
only once a seller sets it, ``refund``/``original``/``new`` only on the matching
message variant. While those keys were undeclared, reading one from a response
that omitted it raised ``AttributeError``. The populated side of each field is
covered by the documented-payload corpus; these tests pin the absent side.
"""

from __future__ import annotations

from discogs_sdk.models.marketplace import Listing, Order, OrderMessage
from discogs_sdk.models.release import MarketplaceReleaseStats
from discogs_sdk.models.user import User
from tests.conftest import make_listing, make_order, make_order_message, make_user


class TestListing:
    def test_owner_only_fields_absent_for_other_viewers(self) -> None:
        listing = Listing.model_validate(make_listing())
        assert listing.weight is None
        assert listing.format_quantity is None
        assert listing.external_id is None
        assert listing.location is None
        assert listing.quantity is None
        assert listing.in_cart is None

    def test_original_shipping_price_absent(self) -> None:
        assert Listing.model_validate(make_listing()).original_shipping_price is None

    def test_release_summary_fields_absent(self) -> None:
        listing = Listing.model_validate(make_listing() | {"release": {"id": 352665}})
        assert listing.release is not None
        assert listing.release.artist is None
        assert listing.release.title is None
        assert listing.release.format is None


class TestOrder:
    def test_tracking_absent_until_the_seller_sets_it(self) -> None:
        assert Order.model_validate(make_order()).tracking is None

    def test_item_conditions_absent(self) -> None:
        order = Order.model_validate(make_order() | {"items": [{"id": 41578242}]})
        assert order.items is not None
        assert order.items[0].media_condition is None
        assert order.items[0].sleeve_condition is None


class TestOrderMessage:
    def test_variant_fields_absent(self) -> None:
        message = OrderMessage.model_validate(make_order_message())
        assert message.refund is None
        assert message.original is None
        assert message.new is None


class TestMarketplaceReleaseStats:
    def test_blocked_from_sale_absent(self) -> None:
        assert MarketplaceReleaseStats.model_validate({}).blocked_from_sale is None


class TestUser:
    def test_email_absent_for_other_users(self) -> None:
        assert User.model_validate(make_user()).email is None
