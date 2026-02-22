from __future__ import annotations

from discogs_sdk._async._lazy import AsyncLazyResource
from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk.models.list_ import List_, ListSummary


class UserLists(AsyncAPIResource):
    """User's lists: GET /users/{username}/lists (paginated)."""

    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def list(
        self,
        *,
        page: int | None = None,
        per_page: int | None = None,
    ) -> AsyncPage[ListSummary]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return AsyncPage(
            client=self._client,
            items_key="lists",
            model_cls=ListSummary,
            params=params,
            path=f"/users/{self._username}/lists",
        )


class Lists(AsyncAPIResource):
    """Top-level list access: GET /lists/{id}."""

    def get(self, list_id: int) -> AsyncLazyResource:
        return AsyncLazyResource(
            client=self._client,
            model_cls=List_,
            path=f"/lists/{list_id}",
        )
