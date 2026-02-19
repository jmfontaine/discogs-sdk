# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations
from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models.release import (
    CommunityRating,
    MarketplaceReleaseStats,
    PriceSuggestions,
    Release,
    ReleaseStats,
    UserReleaseRating,
)


class ReleaseRating(SyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self, username: str | None = None) -> LazyResource:
        if username:
            return LazyResource(
                client=self._client, model_cls=UserReleaseRating, path=f"/releases/{self._release_id}/rating/{username}"
            )
        return LazyResource(client=self._client, model_cls=CommunityRating, path=f"/releases/{self._release_id}/rating")

    def update(self, username: str, rating: int) -> UserReleaseRating:
        response = self._put(f"/releases/{self._release_id}/rating/{username}", json={"rating": rating})
        return self._parse_response(response, UserReleaseRating)

    def delete(self, username: str) -> None:
        response = self._delete(f"/releases/{self._release_id}/rating/{username}")
        self._raise_for_error(response)


class ReleaseStatsResource(SyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self) -> LazyResource:
        return LazyResource(client=self._client, model_cls=ReleaseStats, path=f"/releases/{self._release_id}/stats")


class ReleasePriceSuggestions(SyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self) -> LazyResource:
        return LazyResource(
            client=self._client, model_cls=PriceSuggestions, path=f"/marketplace/price_suggestions/{self._release_id}"
        )


class ReleaseMarketplaceStats(SyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self) -> LazyResource:
        return LazyResource(
            client=self._client, model_cls=MarketplaceReleaseStats, path=f"/marketplace/stats/{self._release_id}"
        )


class Releases(SyncAPIResource):
    def get(self, release_id: int) -> LazyResource:
        return LazyResource(
            client=self._client,
            path=f"/releases/{release_id}",
            model_cls=Release,
            sub_resources={
                "marketplace_stats": lambda: ReleaseMarketplaceStats(self._client, release_id),
                "price_suggestions": lambda: ReleasePriceSuggestions(self._client, release_id),
                "rating": lambda: ReleaseRating(self._client, release_id),
                "stats": lambda: ReleaseStatsResource(self._client, release_id),
            },
        )
