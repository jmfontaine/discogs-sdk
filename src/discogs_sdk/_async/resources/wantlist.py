from __future__ import annotations

from typing import Any

from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk.models.wantlist import Want


class Wantlist(AsyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def list(
        self,
        *,
        page: int | None = None,
        per_page: int | None = None,
    ) -> AsyncPage[Want]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return AsyncPage(
            client=self._client,
            path=f"/users/{self._username}/wants",
            params=params,
            model_cls=Want,
            items_key="wants",
        )

    async def create(self, *, release_id: int, notes: str | None = None, rating: int | None = None) -> Want:
        body = {k: v for k, v in {"notes": notes, "rating": rating}.items() if v is not None}
        response = await self._put(f"/users/{self._username}/wants/{release_id}", json=body)
        return self._parse_response(response, Want)

    async def delete(self, release_id: int) -> None:
        response = await self._delete(f"/users/{self._username}/wants/{release_id}")
        self._raise_for_error(response)

    async def update(self, release_id: int, **kwargs: Any) -> Want:
        response = await self._post(f"/users/{self._username}/wants/{release_id}", json=kwargs)
        return self._parse_response(response, Want)
