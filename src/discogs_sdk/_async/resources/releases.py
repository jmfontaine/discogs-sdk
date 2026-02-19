from __future__ import annotations

from discogs_sdk._async._lazy import AsyncLazyResource
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk.models.release import (
    CommunityRating,
    MarketplaceReleaseStats,
    PriceSuggestions,
    Release,
    ReleaseStats,
    UserReleaseRating,
)


class ReleaseRating(AsyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self, username: str | None = None) -> AsyncLazyResource:
        if username:
            return AsyncLazyResource(
                client=self._client,
                model_cls=UserReleaseRating,
                path=f"/releases/{self._release_id}/rating/{username}",
            )
        return AsyncLazyResource(
            client=self._client,
            model_cls=CommunityRating,
            path=f"/releases/{self._release_id}/rating",
        )

    async def update(self, username: str, rating: int) -> UserReleaseRating:
        response = await self._put(
            f"/releases/{self._release_id}/rating/{username}",
            json={"rating": rating},
        )
        return self._parse_response(response, UserReleaseRating)

    async def delete(self, username: str) -> None:
        response = await self._delete(f"/releases/{self._release_id}/rating/{username}")
        self._raise_for_error(response)


class ReleaseStatsResource(AsyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self) -> AsyncLazyResource:
        return AsyncLazyResource(
            client=self._client,
            model_cls=ReleaseStats,
            path=f"/releases/{self._release_id}/stats",
        )


class ReleasePriceSuggestions(AsyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self) -> AsyncLazyResource:
        return AsyncLazyResource(
            client=self._client,
            model_cls=PriceSuggestions,
            path=f"/marketplace/price_suggestions/{self._release_id}",
        )


class ReleaseMarketplaceStats(AsyncAPIResource):
    def __init__(self, client, release_id: int) -> None:
        super().__init__(client)
        self._release_id = release_id

    def get(self) -> AsyncLazyResource:
        return AsyncLazyResource(
            client=self._client,
            model_cls=MarketplaceReleaseStats,
            path=f"/marketplace/stats/{self._release_id}",
        )


class Releases(AsyncAPIResource):
    def get(self, release_id: int) -> AsyncLazyResource:
        return AsyncLazyResource(
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
