from __future__ import annotations

from typing import Any

from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk.models.search import SearchResult


class SearchResource(AsyncAPIResource):
    def __call__(self, **params: Any) -> AsyncPage[SearchResult]:
        api_params: dict[str, Any] = {}
        for k, v in params.items():
            if v is not None:
                api_params["q" if k == "query" else k] = v
        return AsyncPage(
            client=self._client,
            items_key="results",
            model_cls=SearchResult,
            params=api_params,
            path="/database/search",
        )
