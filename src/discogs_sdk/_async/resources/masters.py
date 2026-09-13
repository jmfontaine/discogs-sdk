from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from discogs_sdk._async._lazy import AsyncLazyResource
from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk.models.master import Master, MasterVersion

if TYPE_CHECKING:
    from discogs_sdk._async._client import AsyncDiscogs


class MasterVersions(AsyncAPIResource):
    def __init__(self, client, master_id: int) -> None:
        super().__init__(client)
        self._master_id = master_id

    def list(
        self,
        *,
        format: str | None = None,
        label: str | None = None,
        released: str | None = None,
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
                "label": label,
                "released": released,
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


class MasterProxy(AsyncLazyResource[Master]):
    """Lazy ``Master`` with its typed sub-resources."""

    _master_id: int

    def __init__(self, client: AsyncDiscogs, master_id: int) -> None:
        super().__init__(client, f"/masters/{master_id}", Master)
        self._master_id = master_id

    @cached_property
    def versions(self) -> MasterVersions:
        return MasterVersions(self._client, self._master_id)


class Masters(AsyncAPIResource):
    def get(self, master_id: int) -> MasterProxy:
        return MasterProxy(self._client, master_id)
