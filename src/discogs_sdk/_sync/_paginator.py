# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel

from discogs_sdk._exceptions import DiscogsError

if TYPE_CHECKING:
    from discogs_sdk._sync._client import Discogs
T = TypeVar("T", bound=BaseModel)
_Shape = TypeVar("_Shape")
# How a decoded JSON value is named in a malformed-envelope message.
_JSON_TYPES: dict[type, str] = {
    dict: "an object",
    list: "an array",
    str: "a string",
    int: "a number",
    float: "a number",
    bool: "a boolean",
    type(None): "null",
}


class SyncPage(Generic[T]):
    """Auto-paging iterator over Discogs paginated responses.

    Discogs pagination format::

        {
            "pagination": {"page": 1, "pages": 5, "urls": {"next": "..."}},
            "<items_key>": [...]
        }

    For nested responses (e.g. submissions), set ``items_path`` to traverse
    into the response body before extracting items::

        {"submissions": {"releases": [...]}}
        items_path=["submissions", "releases"]

    A body of any other shape raises ``DiscogsError`` and leaves the iterator
    where it was. An absent ``pagination`` means no next page, and an absent
    items key, at any depth, is an empty page.
    """

    def __init__(
        self,
        client: Discogs,
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
        self._urls: dict[str, str] = {}
        self._next_url: str | None = None
        self._exhausted = False
        self._first_page_fetched = False
        self._page_number: int | None = None
        self._per_page: int | None = None
        self._total_items: int | None = None
        self._total_pages: int | None = None

    def _fetch_page(self) -> None:
        if self._next_url:
            response = self._client._send(
                "GET", self._client._resolve_next_url(self._next_url)
            )
        else:
            response = self._client._send(
                "GET", self._client._build_url(self._path), params=self._params
            )
        body = self._expect("response body", response.json(), dict)
        # An absent "pagination" means no metadata and no next page.
        pagination = self._expect('"pagination"', body.get("pagination", {}), dict)
        page_number = pagination.get("page")
        per_page = pagination.get("per_page")
        total_items = pagination.get("items")
        total_pages = pagination.get("pages")
        # The reference documents first/prev/next/last; only "next" drives the
        # iterator, but all four are worth surfacing. Null or empty means none.
        urls = self._expect('"pagination.urls"', pagination.get("urls") or {}, dict)
        next_url = urls.get("next")
        # The flat items key is a path of one step. An absent key at any depth is
        # an empty page: a page of /users/{username}/submissions can carry only
        # some categories.
        keys = self._items_path or [self._items_key]
        container: dict[str, Any] = body
        raw_items: list[Any] = []
        for depth, key in enumerate(keys, start=1):
            if key not in container:
                break
            name = f'"{".".join(keys[:depth])}"'
            if depth < len(keys):
                container = self._expect(name, container[key], dict)
            else:
                raw_items = self._expect(name, container[key], list)
        items = [self._model_cls.model_validate(item) for item in raw_items]
        # Commit only once the whole page has parsed: a page that raises above
        # leaves the paginator as it was, so the next call requests it again.
        self._page_number = page_number
        self._per_page = per_page
        self._total_items = total_items
        self._total_pages = total_pages
        self._urls = urls
        self._next_url = next_url
        if not next_url:
            self._exhausted = True
        self._items = items
        self._index = 0
        self._first_page_fetched = True

    def _expect(self, name: str, value: object, expected: type[_Shape]) -> _Shape:
        """Return *value* when it is an *expected*, else raise ``DiscogsError``.

        The message names the endpoint, *name* and the JSON type received, never
        the value itself.
        """
        if isinstance(value, expected):
            return value
        raise DiscogsError(
            f"GET {self._path}: {name} is {_JSON_TYPES[type(value)]}, expected {_JSON_TYPES[expected]}"
        )

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

    @property
    def first_url(self) -> str | None:
        """URL of the first page, or ``None`` when the response omits it."""
        return self._urls.get("first")

    @property
    def prev_url(self) -> str | None:
        """URL of the previous page, or ``None`` when the response omits it."""
        return self._urls.get("prev")

    @property
    def next_url(self) -> str | None:
        """URL of the next page, or ``None`` on the last page."""
        return self._urls.get("next")

    @property
    def last_url(self) -> str | None:
        """URL of the last page, or ``None`` when the response omits it."""
        return self._urls.get("last")

    def __iter__(self) -> Iterator[T]:
        return self

    def __next__(self) -> T:
        if not self._first_page_fetched:
            self._fetch_page()
        # A page can carry none of the selected items and still have successors:
        # /users/{username}/submissions splits each page into releases, artists
        # and labels, so one category is often empty mid-run. Keep fetching until
        # an item turns up or the API stops offering a next page.
        while self._index >= len(self._items):
            if self._exhausted:
                raise StopIteration
            self._fetch_page()
        item = self._items[self._index]
        self._index += 1
        return item
