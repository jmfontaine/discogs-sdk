from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from discogs_sdk._async._lazy import AsyncLazyResource
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk.models._common import CurrencyCode
from discogs_sdk.models.release import (
    CommunityRating,
    MarketplaceReleaseStats,
    PriceSuggestions,
    Release,
    ReleaseStats,
    UserReleaseRating,
)

if TYPE_CHECKING:
    from discogs_sdk._async._client import AsyncDiscogs


class CommunityRatingProxy(AsyncLazyResource[CommunityRating]):
    """Lazy community rating for a release."""


class UserReleaseRatingProxy(AsyncLazyResource[UserReleaseRating]):
    """Lazy rating a single user gave a release."""


class ReleaseStatsProxy(AsyncLazyResource[ReleaseStats]):
    """Lazy have/want counts for a release."""


class PriceSuggestionsProxy(AsyncLazyResource[PriceSuggestions]):
    """Lazy suggested prices per condition for a release."""


class MarketplaceReleaseStatsProxy(AsyncLazyResource[MarketplaceReleaseStats]):
    """Lazy marketplace statistics for a release."""


class ReleaseRating(AsyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self, username: str | None = None) -> CommunityRatingProxy | UserReleaseRatingProxy:
        if username:
            return UserReleaseRatingProxy(
                self._client,
                f"/releases/{self._release_id}/rating/{username}",
                UserReleaseRating,
            )
        return CommunityRatingProxy(
            self._client,
            f"/releases/{self._release_id}/rating",
            CommunityRating,
        )

    async def update(self, username: str, rating: int) -> UserReleaseRating:
        response = await self._put(
            f"/releases/{self._release_id}/rating/{username}",
            json={"rating": rating},
        )
        return self._parse_response(response, UserReleaseRating)

    async def delete(self, username: str) -> None:
        await self._delete(f"/releases/{self._release_id}/rating/{username}")


class ReleaseStatsResource(AsyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self) -> ReleaseStatsProxy:
        return ReleaseStatsProxy(self._client, f"/releases/{self._release_id}/stats", ReleaseStats)


class ReleasePriceSuggestions(AsyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self) -> PriceSuggestionsProxy:
        return PriceSuggestionsProxy(
            self._client,
            f"/marketplace/price_suggestions/{self._release_id}",
            PriceSuggestions,
        )


class ReleaseMarketplaceStats(AsyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self, *, curr_abbr: CurrencyCode | None = None) -> MarketplaceReleaseStatsProxy:
        """Marketplace stats for the release, priced in *curr_abbr* when given."""
        return MarketplaceReleaseStatsProxy(
            self._client,
            f"/marketplace/stats/{self._release_id}",
            MarketplaceReleaseStats,
            params={"curr_abbr": curr_abbr} if curr_abbr else None,
        )


class ReleaseProxy(AsyncLazyResource[Release]):
    """Lazy ``Release`` with its typed sub-resources."""

    _release_id: int

    def __init__(self, client: AsyncDiscogs, release_id: int, *, curr_abbr: CurrencyCode | None = None) -> None:
        super().__init__(
            client,
            f"/releases/{release_id}",
            Release,
            params={"curr_abbr": curr_abbr} if curr_abbr else None,
        )
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


class Releases(AsyncAPIResource):
    def get(self, release_id: int, *, curr_abbr: CurrencyCode | None = None) -> ReleaseProxy:
        """The release, with marketplace prices in *curr_abbr* when given."""
        return ReleaseProxy(self._client, release_id, curr_abbr=curr_abbr)
