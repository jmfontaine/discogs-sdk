# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations
from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models.label import Label, LabelRelease


class LabelReleases(SyncAPIResource):
    def __init__(self, client, label_id: int) -> None:
        super().__init__(client)
        self._label_id = label_id

    def list(self) -> SyncPage[LabelRelease]:
        return SyncPage(
            client=self._client, items_key="releases", model_cls=LabelRelease, path=f"/labels/{self._label_id}/releases"
        )


class Labels(SyncAPIResource):
    def get(self, label_id: int) -> LazyResource:
        return LazyResource(
            client=self._client,
            model_cls=Label,
            path=f"/labels/{label_id}",
            sub_resources={"releases": lambda: LabelReleases(self._client, label_id)},
        )
