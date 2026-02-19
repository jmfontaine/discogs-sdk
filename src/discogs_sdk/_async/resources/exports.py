from __future__ import annotations

from discogs_sdk._async._lazy import AsyncLazyResource
from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk.models.export import Export


class Exports(AsyncAPIResource):
    def get(self, export_id: int) -> AsyncLazyResource:
        return AsyncLazyResource(
            client=self._client,
            model_cls=Export,
            path=f"/inventory/export/{export_id}",
        )

    def list(self) -> AsyncPage[Export]:
        return AsyncPage(
            client=self._client,
            items_key="items",
            model_cls=Export,
            path="/inventory/export",
        )

    async def download(self, export_id: int) -> bytes:
        return await self._get_binary(f"/inventory/export/{export_id}/download")

    async def request(self) -> None:
        response = await self._post("/inventory/export")
        self._raise_for_error(response)
