# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models._lazy_fields import LabelFields
from discogs_sdk.models.label import Label, LabelRelease

if TYPE_CHECKING:
    from discogs_sdk._sync._client import Discogs


class LabelReleases(SyncAPIResource):
    def __init__(self, client, label_id: int) -> None:
        super().__init__(client)
        self._label_id = label_id

    def list(self, *, page: int | None = None, per_page: int | None = None) -> SyncPage[LabelRelease]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return SyncPage(
            client=self._client,
            items_key="releases",
            model_cls=LabelRelease,
            params=params,
            path=f"/labels/{self._label_id}/releases",
        )


class LabelProxy(LazyResource[Label], LabelFields):
    """Lazy ``Label`` with its typed sub-resources."""

    _label_id: int

    def __init__(self, client: Discogs, label_id: int) -> None:
        super().__init__(client, f"/labels/{label_id}", Label)
        self._label_id = label_id

    @cached_property
    def releases(self) -> LabelReleases:
        return LabelReleases(self._client, self._label_id)


class Labels(SyncAPIResource):
    def get(self, label_id: int) -> LabelProxy:
        return LabelProxy(self._client, label_id)
