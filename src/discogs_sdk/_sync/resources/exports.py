# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations
from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models.export import Export


class Exports(SyncAPIResource):
    def get(self, export_id: int) -> LazyResource:
        return LazyResource(client=self._client, model_cls=Export, path=f"/inventory/export/{export_id}")

    def list(self) -> SyncPage[Export]:
        return SyncPage(client=self._client, items_key="items", model_cls=Export, path="/inventory/export")

    def download(self, export_id: int) -> bytes:
        return self._get_binary(f"/inventory/export/{export_id}/download")

    def request(self) -> None:
        response = self._post("/inventory/export")
        self._raise_for_error(response)
