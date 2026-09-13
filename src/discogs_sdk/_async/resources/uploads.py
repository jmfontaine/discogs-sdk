from __future__ import annotations

from discogs_sdk._async._lazy import AsyncLazyResource
from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk.models.upload import Upload


class UploadProxy(AsyncLazyResource[Upload]):
    """Lazy inventory upload."""


class Uploads(AsyncAPIResource):
    async def create(self, *, file: str) -> None:
        await self._post_file("/inventory/upload/add", file_path=file)

    async def change(self, *, file: str) -> None:
        await self._post_file("/inventory/upload/change", file_path=file)

    async def delete(self, *, file: str) -> None:
        await self._post_file("/inventory/upload/delete", file_path=file)

    def list(
        self,
        *,
        page: int | None = None,
        per_page: int | None = None,
    ) -> AsyncPage[Upload]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return AsyncPage(
            client=self._client,
            items_key="items",
            model_cls=Upload,
            params=params,
            path="/inventory/upload",
        )

    def get(self, upload_id: int) -> UploadProxy:
        return UploadProxy(self._client, f"/inventory/upload/{upload_id}", Upload)
