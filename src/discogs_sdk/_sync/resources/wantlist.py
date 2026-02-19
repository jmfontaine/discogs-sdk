# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations
from typing import Any
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models.wantlist import Want


class Wantlist(SyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def list(self) -> SyncPage[Want]:
        return SyncPage(client=self._client, path=f"/users/{self._username}/wants", model_cls=Want, items_key="wants")

    def create(self, *, release_id: int, notes: str | None = None, rating: int | None = None) -> Want:
        body = {k: v for k, v in {"notes": notes, "rating": rating}.items() if v is not None}
        response = self._put(f"/users/{self._username}/wants/{release_id}", json=body)
        return self._parse_response(response, Want)

    def delete(self, release_id: int) -> None:
        response = self._delete(f"/users/{self._username}/wants/{release_id}")
        self._raise_for_error(response)

    def update(self, release_id: int, **kwargs: Any) -> Want:
        response = self._post(f"/users/{self._username}/wants/{release_id}", json=kwargs)
        return self._parse_response(response, Want)
