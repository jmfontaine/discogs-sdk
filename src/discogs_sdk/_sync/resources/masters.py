# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations
from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models.master import Master, MasterVersion


class MasterVersions(SyncAPIResource):
    def __init__(self, client, master_id: int) -> None:
        super().__init__(client)
        self._master_id = master_id

    def list(
        self,
        *,
        format: str | None = None,
        country: str | None = None,
        sort: str | None = None,
        sort_order: str | None = None,
    ) -> SyncPage[MasterVersion]:
        params = {
            k: v for k, v in {"format": format, "country": country, "sort": sort, "sort_order": sort_order}.items() if v
        }
        return SyncPage(
            client=self._client,
            items_key="versions",
            model_cls=MasterVersion,
            params=params,
            path=f"/masters/{self._master_id}/versions",
        )


class Masters(SyncAPIResource):
    def get(self, master_id: int) -> LazyResource:
        return LazyResource(
            client=self._client,
            model_cls=Master,
            path=f"/masters/{master_id}",
            sub_resources={"versions": lambda: MasterVersions(self._client, master_id)},
        )
