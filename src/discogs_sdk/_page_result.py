"""The snapshot of one page of a paginated listing that ``fetch()`` returns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class PageResult(Generic[T]):
    """One page of a listing, fetched on its own by ``AsyncPage.fetch()`` or ``SyncPage.fetch()``.

    A snapshot: it never sends a request and is independent of the page object
    that produced it. Attributes cannot be reassigned. It compares by value and
    pickles and copies like the other SDK value types, but is not hashable,
    since ``items`` and ``urls`` are a list and a dict.

    Attributes:
        items: The page's items, validated like the items iteration yields.
        page: Page number, as Discogs reports it; ``None`` when it does not.
        per_page: Items per page, as Discogs reports it; ``None`` when it does not.
        total_items: Items across all pages, when the response supplies it.
        total_pages: Number of pages, when the response supplies it.
        urls: The response's ``pagination.urls`` (``first``, ``prev``, ``next``,
            ``last``), holding only the links it supplied.
    """

    items: list[T]
    page: int | None
    per_page: int | None
    total_items: int | None
    total_pages: int | None
    urls: dict[str, str]

    # Declared so hash() names this class; the generated one fails on items.
    __hash__: ClassVar[None] = None  # type: ignore[assignment]
