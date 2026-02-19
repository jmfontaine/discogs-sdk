# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations
from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models.list_ import List_, ListSummary


class UserLists(SyncAPIResource):
    """User's lists: GET /users/{username}/lists (paginated)."""

    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def list(self) -> SyncPage[ListSummary]:
        return SyncPage(
            client=self._client, items_key="lists", model_cls=ListSummary, path=f"/users/{self._username}/lists"
        )


class Lists(SyncAPIResource):
    """Top-level list access: GET /lists/{id}."""

    def get(self, list_id: int) -> LazyResource:
        return LazyResource(client=self._client, model_cls=List_, path=f"/lists/{list_id}")
