from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncIterator, Generic, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from discogs_sdk._async._client import AsyncDiscogs

T = TypeVar("T", bound=BaseModel)


class AsyncPage(Generic[T]):
    """Auto-paging async iterator over Discogs paginated responses.

    Discogs pagination format::

        {
            "pagination": {"page": 1, "pages": 5, "urls": {"next": "..."}},
            "<items_key>": [...]
        }

    For nested responses (e.g. submissions), set ``items_path`` to traverse
    into the response body before extracting items::

        {"submissions": {"releases": [...]}}
        items_path=["submissions", "releases"]
    """

    def __init__(
        self,
        client: AsyncDiscogs,
        path: str,
        model_cls: type[T],
        items_key: str,
        *,
        params: dict[str, Any] | None = None,
        items_path: list[str] | None = None,
    ) -> None:
        self._client = client
        self._path = path
        self._params = {"page": 1, **(params or {})}
        self._model_cls = model_cls
        self._items_key = items_key
        self._items_path = items_path

        self._items: list[T] = []
        self._index = 0
        self._next_url: str | None = None
        self._exhausted = False
        self._first_page_fetched = False

        self._page_number: int | None = None
        self._per_page: int | None = None
        self._total_items: int | None = None
        self._total_pages: int | None = None

    async def _fetch_page(self) -> None:
        if self._next_url:
            response = await self._client._send("GET", self._next_url)
        else:
            response = await self._client._send(
                "GET",
                self._client._build_url(self._path),
                params=self._params,
            )

        body = response.json()
        self._client._maybe_raise(response.status_code, body, retry_after=response.headers.get("Retry-After"))

        pagination = body.get("pagination", {})
        self._page_number = pagination.get("page")
        self._per_page = pagination.get("per_page")
        self._total_items = pagination.get("items")
        self._total_pages = pagination.get("pages")

        urls = pagination.get("urls", {})
        self._next_url = urls.get("next")
        if not self._next_url:
            self._exhausted = True

        if self._items_path:
            container = body
            for key in self._items_path:
                container = container.get(key, {})
            raw_items = container if isinstance(container, list) else []
        else:
            raw_items = body.get(self._items_key, [])

        self._items = [self._model_cls.model_validate(item) for item in raw_items]
        self._index = 0
        self._first_page_fetched = True

    @property
    def page(self) -> int | None:
        """Current page number, or ``None`` if no page has been fetched yet."""
        return self._page_number

    @property
    def per_page(self) -> int | None:
        """Number of items per page, or ``None`` if no page has been fetched yet."""
        return self._per_page

    @property
    def total_items(self) -> int | None:
        """Total number of items across all pages, or ``None`` if no page has been fetched yet."""
        return self._total_items

    @property
    def total_pages(self) -> int | None:
        """Total number of pages, or ``None`` if no page has been fetched yet."""
        return self._total_pages

    def __aiter__(self) -> AsyncIterator[T]:
        return self

    async def __anext__(self) -> T:
        if not self._first_page_fetched:
            await self._fetch_page()

        if self._index >= len(self._items):
            if self._exhausted:
                raise StopAsyncIteration
            await self._fetch_page()
            if not self._items:
                raise StopAsyncIteration

        item = self._items[self._index]
        self._index += 1
        return item
