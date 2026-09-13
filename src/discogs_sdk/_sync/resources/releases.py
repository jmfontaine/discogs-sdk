# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models._lazy_fields import (
    CommunityRatingFields,
    MarketplaceReleaseStatsFields,
    PriceSuggestionsFields,
    ReleaseFields,
    ReleaseStatsFields,
    UserReleaseRatingFields,
)
from discogs_sdk.models.release import (
    CommunityRating,
    MarketplaceReleaseStats,
    PriceSuggestions,
    Release,
    ReleaseStats,
    UserReleaseRating,
)

if TYPE_CHECKING:
    from discogs_sdk._sync._client import Discogs


class CommunityRatingProxy(LazyResource[CommunityRating], CommunityRatingFields):
    """Lazy community rating for a release."""


class UserReleaseRatingProxy(LazyResource[UserReleaseRating], UserReleaseRatingFields):
    """Lazy rating a single user gave a release."""


class ReleaseStatsProxy(LazyResource[ReleaseStats], ReleaseStatsFields):
    """Lazy have/want counts for a release."""


class PriceSuggestionsProxy(LazyResource[PriceSuggestions], PriceSuggestionsFields):
    """Lazy suggested prices per condition for a release."""


class MarketplaceReleaseStatsProxy(LazyResource[MarketplaceReleaseStats], MarketplaceReleaseStatsFields):
    """Lazy marketplace statistics for a release."""


class ReleaseRating(SyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self, username: str | None = None) -> CommunityRatingProxy | UserReleaseRatingProxy:
        if username:
            return UserReleaseRatingProxy(
                self._client, f"/releases/{self._release_id}/rating/{username}", UserReleaseRating
            )
        return CommunityRatingProxy(self._client, f"/releases/{self._release_id}/rating", CommunityRating)

    def update(self, username: str, rating: int) -> UserReleaseRating:
        response = self._put(f"/releases/{self._release_id}/rating/{username}", json={"rating": rating})
        return self._parse_response(response, UserReleaseRating)

    def delete(self, username: str) -> None:
        self._delete(f"/releases/{self._release_id}/rating/{username}")


class ReleaseStatsResource(SyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self) -> ReleaseStatsProxy:
        return ReleaseStatsProxy(self._client, f"/releases/{self._release_id}/stats", ReleaseStats)


class ReleasePriceSuggestions(SyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self) -> PriceSuggestionsProxy:
        return PriceSuggestionsProxy(
            self._client, f"/marketplace/price_suggestions/{self._release_id}", PriceSuggestions
        )


class ReleaseMarketplaceStats(SyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self) -> MarketplaceReleaseStatsProxy:
        return MarketplaceReleaseStatsProxy(
            self._client, f"/marketplace/stats/{self._release_id}", MarketplaceReleaseStats
        )


class ReleaseProxy(LazyResource[Release], ReleaseFields):
    """Lazy ``Release`` with its typed sub-resources."""

    _release_id: int

    def __init__(self, client: Discogs, release_id: int) -> None:
        super().__init__(client, f"/releases/{release_id}", Release)
        self._release_id = release_id

    @cached_property
    def marketplace_stats(self) -> ReleaseMarketplaceStats:
        return ReleaseMarketplaceStats(self._client, self._release_id)

    @cached_property
    def price_suggestions(self) -> ReleasePriceSuggestions:
        return ReleasePriceSuggestions(self._client, self._release_id)

    @cached_property
    def rating(self) -> ReleaseRating:
        return ReleaseRating(self._client, self._release_id)

    @cached_property
    def stats(self) -> ReleaseStatsResource:
        return ReleaseStatsResource(self._client, self._release_id)


class Releases(SyncAPIResource):
    def get(self, release_id: int) -> ReleaseProxy:
        return ReleaseProxy(self._client, release_id)
