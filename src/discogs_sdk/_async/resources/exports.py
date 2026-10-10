from __future__ import annotations

from discogs_sdk._async._lazy import AsyncLazyResource
from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk._base_client import path_segment
from discogs_sdk.models.export import Export


class ExportProxy(AsyncLazyResource[Export]):
    """Lazy inventory export."""


class Exports(AsyncAPIResource):
    def get(self, export_id: int) -> ExportProxy:
        """Lazy export status. Its request bypasses the response cache, so every
        new proxy sees the current status; a resolved proxy keeps its data, so poll
        with a new ``get()`` call each time."""
        return ExportProxy(
            self._client,
            f"/inventory/export/{path_segment(export_id)}",
            Export,
            cacheable=False,
        )

    def list(
        self,
        *,
        page: int | None = None,
        per_page: int | None = None,
    ) -> AsyncPage[Export]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return AsyncPage(
            client=self._client,
            items_key="items",
            model_cls=Export,
            params=params,
            path="/inventory/export",
        )

    async def download(self, export_id: int) -> bytes:
        return await self._get_binary(
            f"/inventory/export/{path_segment(export_id)}/download"
        )

    async def request(self) -> None:
        await self._post("/inventory/export")
