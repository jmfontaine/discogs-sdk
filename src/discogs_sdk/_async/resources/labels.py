from __future__ import annotations

from discogs_sdk._async._lazy import AsyncLazyResource
from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk.models.label import Label, LabelRelease


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


class Labels(AsyncAPIResource):
    def get(self, label_id: int) -> AsyncLazyResource:
        return AsyncLazyResource(
            client=self._client,
            model_cls=Label,
            path=f"/labels/{label_id}",
            sub_resources={
                "releases": lambda: LabelReleases(self._client, label_id),
            },
        )
