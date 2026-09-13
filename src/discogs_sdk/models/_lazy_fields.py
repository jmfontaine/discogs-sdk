# This file is auto-generated from the model definitions.
# Do not edit directly — edit the models in discogs_sdk/models/ instead.
"""Declared members of every model reachable through a lazy proxy.

A sync proxy resolves on attribute access, so consumers read model members
straight off the proxy. These mixins declare those members — and only those —
so a misspelled name is a static error rather than a dynamic ``Any``.

Everything is declared under ``TYPE_CHECKING``: at runtime the classes are
empty, which leaves the proxy's ``__getattr__`` free to resolve and delegate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discogs_sdk.models._common import (
        ArtistCredit,
        Community,
        Company,
        Condition,
        CurrencyCode,
        Format,
        Identifier,
        Image,
        LabelCredit,
        Member,
        Price,
        SleeveCondition,
        SubLabel,
        Track,
        UserSummary,
        Video,
    )
    from discogs_sdk.models.list_ import ListItem
    from discogs_sdk.models.marketplace import ListingRelease, OrderItem, OriginalPrice, ShippingInfo
    from discogs_sdk.models.release import RatingInfo


class ArtistFields:
    """Members of :class:`Artist`."""

    if TYPE_CHECKING:
        id: int
        data_quality: str | None
        images: list[Image] | None
        members: list[Member] | None
        name_variations: list[str] | None
        name: str
        profile: str | None
        releases_url: str | None
        resource_url: str | None
        uri: str | None
        urls: list[str] | None


class CollectionFolderFields:
    """Members of :class:`CollectionFolder`."""

    if TYPE_CHECKING:
        id: int
        count: int | None
        name: str
        resource_url: str | None


class CollectionValue_Fields:
    """Members of :class:`CollectionValue_`."""

    if TYPE_CHECKING:
        maximum: str | None
        median: str | None
        minimum: str | None


class CommunityRatingFields:
    """Members of :class:`CommunityRating`."""

    if TYPE_CHECKING:
        rating: RatingInfo
        release_id: int


class ExportFields:
    """Members of :class:`Export`."""

    if TYPE_CHECKING:
        id: int
        created_at: str | None
        download_url: str | None
        filename: str | None
        finished_at: str | None
        status: str | None
        url: str | None


class FeeFields:
    """Members of :class:`Fee`."""

    if TYPE_CHECKING:
        currency: CurrencyCode | str | None
        value: float


class LabelFields:
    """Members of :class:`Label`."""

    if TYPE_CHECKING:
        id: int
        contact_info: str | None
        data_quality: str | None
        images: list[Image] | None
        name: str
        profile: str | None
        releases_url: str | None
        resource_url: str | None
        sub_labels: list[SubLabel] | None
        uri: str | None
        urls: list[str] | None


class List_Fields:
    """Members of :class:`List_`."""

    if TYPE_CHECKING:
        id: int
        created_at: str | None
        description: str | None
        items: list[ListItem] | None
        modified_at: str | None
        name: str
        public: bool | None
        resource_url: str | None
        url: str | None


class ListingFields:
    """Members of :class:`Listing`."""

    if TYPE_CHECKING:
        id: int
        allow_offers: bool | None
        audio: bool | None
        comments: str | None
        condition: Condition | str | None
        original_price: OriginalPrice | None
        posted: str | None
        price: Price | None
        release: ListingRelease | None
        resource_url: str | None
        seller: UserSummary | None
        shipping_price: Price | None
        ships_from: str | None
        sleeve_condition: SleeveCondition | str | None
        status: str | None
        uri: str | None


class MarketplaceReleaseStatsFields:
    """Members of :class:`MarketplaceReleaseStats`."""

    if TYPE_CHECKING:
        lowest_price: Price | None
        num_for_sale: int | None


class MasterFields:
    """Members of :class:`Master`."""

    if TYPE_CHECKING:
        id: int
        artists: list[ArtistCredit] | None
        data_quality: str | None
        genres: list[str] | None
        images: list[Image] | None
        lowest_price: float | None
        main_release_url: str | None
        main_release: int | None
        num_for_sale: int | None
        resource_url: str | None
        styles: list[str] | None
        title: str
        tracklist: list[Track] | None
        uri: str | None
        versions_url: str | None
        videos: list[Video] | None
        year: int | None


class OrderFields:
    """Members of :class:`Order`."""

    if TYPE_CHECKING:
        id: str
        additional_instructions: str | None
        archived: bool | None
        buyer: UserSummary | None
        created: str | None
        fee: Price | None
        items: list[OrderItem] | None
        last_activity: str | None
        messages_url: str | None
        next_status: list[str] | None
        resource_url: str | None
        seller: UserSummary | None
        shipping_address: str | None
        shipping: ShippingInfo | None
        status: str | None
        total: Price | None
        uri: str | None


class PriceSuggestionsFields:
    """Members of :class:`PriceSuggestions`."""

    if TYPE_CHECKING:

        @property
        def conditions(self) -> dict[str, Price]: ...
        def __getitem__(self, condition: str) -> Price: ...


class ReleaseFields:
    """Members of :class:`Release`."""

    if TYPE_CHECKING:
        id: int
        artists: list[ArtistCredit] | None
        community: Community | None
        companies: list[Company] | None
        country: str | None
        data_quality: str | None
        date_added: str | None
        date_changed: str | None
        estimated_weight: int | None
        extra_artists: list[ArtistCredit] | None
        format_quantity: int | None
        formats: list[Format] | None
        genres: list[str] | None
        identifiers: list[Identifier] | None
        images: list[Image] | None
        labels: list[LabelCredit] | None
        lowest_price: float | None
        master_id: int | None
        master_url: str | None
        notes: str | None
        num_for_sale: int | None
        released_formatted: str | None
        released: str | None
        resource_url: str | None
        series: list[LabelCredit] | None
        status: str | None
        styles: list[str] | None
        thumb: str | None
        title: str
        tracklist: list[Track] | None
        uri: str | None
        videos: list[Video] | None
        year: int | None


class ReleaseStatsFields:
    """Members of :class:`ReleaseStats`."""

    if TYPE_CHECKING:
        num_have: int | None
        num_want: int | None


class UploadFields:
    """Members of :class:`Upload`."""

    if TYPE_CHECKING:
        id: int
        created_at: str | None
        filename: str | None
        finished_at: str | None
        results: str | None
        status: str | None
        type: str | None


class UserFields:
    """Members of :class:`User`."""

    if TYPE_CHECKING:
        id: int
        avatar_url: str | None
        banner_url: str | None
        buyer_num_ratings: int | None
        buyer_rating_stars: float | None
        buyer_rating: float | None
        collection_fields_url: str | None
        collection_folders_url: str | None
        currency_code: str | None
        home_page: str | None
        inventory_url: str | None
        location: str | None
        name: str | None
        num_collection: int | None
        num_for_sale: int | None
        num_lists: int | None
        num_pending: int | None
        num_wantlist: int | None
        profile: str | None
        rank: int | None
        rating_avg: float | None
        registered: str | None
        releases_contributed: int | None
        releases_rated: int | None
        resource_url: str | None
        seller_num_ratings: int | None
        seller_rating_stars: float | None
        seller_rating: float | None
        uri: str | None
        username: str
        wantlist_url: str | None


class UserReleaseRatingFields:
    """Members of :class:`UserReleaseRating`."""

    if TYPE_CHECKING:
        rating: int
        release_id: int
        username: str
