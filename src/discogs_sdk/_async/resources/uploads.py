from __future__ import annotations

from discogs_sdk._async._lazy import AsyncLazyResource
from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk.models.upload import Upload


class Uploads(AsyncAPIResource):
    async def create(self, *, file: str) -> None:
        response = await self._post_file("/inventory/upload/add", file_path=file)
        self._raise_for_error(response)

    async def change(self, *, file: str) -> None:
        response = await self._post_file("/inventory/upload/change", file_path=file)
        self._raise_for_error(response)

    async def delete(self, *, file: str) -> None:
        response = await self._post_file("/inventory/upload/delete", file_path=file)
        self._raise_for_error(response)

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

    def get(self, upload_id: int) -> AsyncLazyResource:
        return AsyncLazyResource(
            client=self._client,
            model_cls=Upload,
            path=f"/inventory/upload/{upload_id}",
        )
