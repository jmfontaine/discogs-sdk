# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models._lazy_fields import ArtistFields
from discogs_sdk.models.artist import Artist, ArtistRelease

if TYPE_CHECKING:
    from discogs_sdk._sync._client import Discogs


class ArtistReleases(SyncAPIResource):
    def __init__(self, client, artist_id: int) -> None:
        super().__init__(client)
        self._artist_id = artist_id

    def list(
        self,
        *,
        sort: str | None = None,
        sort_order: str | None = None,
        page: int | None = None,
        per_page: int | None = None,
    ) -> SyncPage[ArtistRelease]:
        params = {
            k: v for k, v in {"sort": sort, "sort_order": sort_order, "page": page, "per_page": per_page}.items() if v
        }
        return SyncPage(
            client=self._client,
            path=f"/artists/{self._artist_id}/releases",
            params=params,
            model_cls=ArtistRelease,
            items_key="releases",
        )


class ArtistProxy(LazyResource[Artist], ArtistFields):
    """Lazy ``Artist`` with its typed sub-resources."""

    _artist_id: int

    def __init__(self, client: Discogs, artist_id: int) -> None:
        super().__init__(client, f"/artists/{artist_id}", Artist)
        self._artist_id = artist_id

    @cached_property
    def releases(self) -> ArtistReleases:
        return ArtistReleases(self._client, self._artist_id)


class Artists(SyncAPIResource):
    def get(self, artist_id: int) -> ArtistProxy:
        return ArtistProxy(self._client, artist_id)
