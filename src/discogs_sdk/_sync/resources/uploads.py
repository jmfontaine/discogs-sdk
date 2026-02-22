# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations
from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models.upload import Upload


class Uploads(SyncAPIResource):
    def create(self, *, file: str) -> None:
        response = self._post_file("/inventory/upload/add", file_path=file)
        self._raise_for_error(response)

    def change(self, *, file: str) -> None:
        response = self._post_file("/inventory/upload/change", file_path=file)
        self._raise_for_error(response)

    def delete(self, *, file: str) -> None:
        response = self._post_file("/inventory/upload/delete", file_path=file)
        self._raise_for_error(response)

    def list(self, *, page: int | None = None, per_page: int | None = None) -> SyncPage[Upload]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return SyncPage(
            client=self._client, items_key="items", model_cls=Upload, params=params, path="/inventory/upload"
        )

    def get(self, upload_id: int) -> LazyResource:
        return LazyResource(client=self._client, model_cls=Upload, path=f"/inventory/upload/{upload_id}")
