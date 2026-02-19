# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations
from typing import Any
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models.search import SearchResult


class SearchResource(SyncAPIResource):
    def __call__(self, **params: Any) -> SyncPage[SearchResult]:
        api_params: dict[str, Any] = {}
        for k, v in params.items():
            if v is not None:
                api_params["q" if k == "query" else k] = v
        return SyncPage(
            client=self._client, items_key="results", model_cls=SearchResult, params=api_params, path="/database/search"
        )
