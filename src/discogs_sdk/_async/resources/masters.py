from __future__ import annotations

from discogs_sdk._async._lazy import AsyncLazyResource
from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk.models.master import Master, MasterVersion


class MasterVersions(AsyncAPIResource):
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
        page: int | None = None,
        per_page: int | None = None,
    ) -> AsyncPage[MasterVersion]:
        params = {
            k: v
            for k, v in {
                "format": format,
                "country": country,
                "sort": sort,
                "sort_order": sort_order,
                "page": page,
                "per_page": per_page,
            }.items()
            if v
        }
        return AsyncPage(
            client=self._client,
            items_key="versions",
            model_cls=MasterVersion,
            params=params,
            path=f"/masters/{self._master_id}/versions",
        )


class Masters(AsyncAPIResource):
    def get(self, master_id: int) -> AsyncLazyResource:
        return AsyncLazyResource(
            client=self._client,
            model_cls=Master,
            path=f"/masters/{master_id}",
            sub_resources={
                "versions": lambda: MasterVersions(self._client, master_id),
            },
        )
