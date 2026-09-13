from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from discogs_sdk._async._lazy import AsyncLazyResource
from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk.models.label import Label, LabelRelease

if TYPE_CHECKING:
    from discogs_sdk._async._client import AsyncDiscogs


class LabelReleases(AsyncAPIResource):
    def __init__(self, client, label_id: int) -> None:
        super().__init__(client)
        self._label_id = label_id

    def list(
        self,
        *,
        page: int | None = None,
        per_page: int | None = None,
    ) -> AsyncPage[LabelRelease]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return AsyncPage(
            client=self._client,
            items_key="releases",
            model_cls=LabelRelease,
            params=params,
            path=f"/labels/{self._label_id}/releases",
        )


class LabelProxy(AsyncLazyResource[Label]):
    """Lazy ``Label`` with its typed sub-resources."""

    _label_id: int

    def __init__(self, client: AsyncDiscogs, label_id: int) -> None:
        super().__init__(client, f"/labels/{label_id}", Label)
        self._label_id = label_id

    @cached_property
    def releases(self) -> LabelReleases:
        return LabelReleases(self._client, self._label_id)


class Labels(AsyncAPIResource):
    def get(self, label_id: int) -> LabelProxy:
        return LabelProxy(self._client, label_id)
