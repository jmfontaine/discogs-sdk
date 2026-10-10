# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations

from typing import Any

from discogs_sdk._base_client import path_segment
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models.wantlist import Want


class Wantlist(SyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def list(
        self, *, page: int | None = None, per_page: int | None = None
    ) -> SyncPage[Want]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return SyncPage(
            client=self._client,
            path=f"/users/{path_segment(self._username)}/wants",
            params=params,
            model_cls=Want,
            items_key="wants",
        )

    def create(self, *, release_id: int) -> Want:
        """Add *release_id* to the wantlist.

        The endpoint takes no other input. Discogs documents ``notes`` and
        ``rating`` here but discards both — sent as a JSON body or as query
        parameters they come back empty, and the reference's own example
        response shows ``"notes": ""``. Set them with :meth:`update`.
        """
        response = self._put(self._want_path(release_id))
        return self._parse_response(response, Want)

    def delete(self, release_id: int) -> None:
        self._delete(self._want_path(release_id))

    def update(self, release_id: int, **kwargs: Any) -> Want:
        response = self._post(self._want_path(release_id), json=kwargs)
        return self._parse_response(response, Want)

    def _want_path(self, release_id: int) -> str:
        return f"/users/{path_segment(self._username)}/wants/{path_segment(release_id)}"
