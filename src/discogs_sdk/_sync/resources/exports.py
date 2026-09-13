# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations

from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models._lazy_fields import ExportFields
from discogs_sdk.models.export import Export


class ExportProxy(LazyResource[Export], ExportFields):
    """Lazy inventory export."""


class Exports(SyncAPIResource):
    def get(self, export_id: int) -> ExportProxy:
        return ExportProxy(self._client, f"/inventory/export/{export_id}", Export)

    def list(self, *, page: int | None = None, per_page: int | None = None) -> SyncPage[Export]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return SyncPage(
            client=self._client, items_key="items", model_cls=Export, params=params, path="/inventory/export"
        )

    def download(self, export_id: int) -> bytes:
        return self._get_binary(f"/inventory/export/{export_id}/download")

    def request(self) -> None:
        self._post("/inventory/export")
