# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

"""Helpers that depend on undocumented Discogs API behaviour.

Re-exported by ``discogs_sdk.experimental``; see that module for the terms.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING, Any

from discogs_sdk._exceptions import DiscogsError
from discogs_sdk._experimental_types import ReleasesAddedSince

if TYPE_CHECKING:
    from discogs_sdk._events import RequestEvent
    from discogs_sdk._sync._client import Discogs
    from discogs_sdk.models.release import Release
# Search parameters releases_added_since() sets itself: another value would
# change the order the scan relies on, or skip the newest results.
_OWNED_PARAMS = ("sort", "sort_order", "page")


def releases_added_since(
    client: Discogs,
    since: date | datetime,
    *,
    max_requests: int | None = None,
    **search_params: Any,
) -> ReleasesAddedSince:
    """Find the releases matching *search_params* added to Discogs since *since*.

    Experimental: the result is complete only while Discogs keeps honouring an
    undocumented sort order, so this function may change or be removed without
    a deprecation period. It follows the rules for undocumented behaviour in the
    SDK's design principles:
    https://github.com/jmfontaine/discogs-sdk/blob/main/README.md#design-principles

    Discogs has no date filter, and search results carry no ``date_added``. This
    searches with ``type="release"``, ``sort="date_added"`` and
    ``sort_order="desc"``, which Discogs answers newest-added first without
    documenting it, one page at a time through ``fetch()``. It looks up each
    result in order with ``client.releases.get()`` to read its ``date_added``,
    keeps the releases added at or after *since*, and stops at the first one
    added before it. Every returned release therefore has a verified
    ``date_added``, and nothing added before *since* is returned. What the scan
    cannot see is a newer release that Discogs sorts after the first older one:
    completeness assumes the sort holds. A looked-up ``date_added`` newer than
    the one before it shows that it does not, and raises ``DiscogsError``.

    A looked-up release without a ``date_added`` is skipped and does not end the
    scan. A release listed twice, because results shifted between pages, is
    looked up and returned once.

    Cost: one search request per page scanned, plus one lookup per release in
    the window, plus one for the release that ends the scan (none when the
    results run out first); a skipped release costs a lookup too. Cache hits
    cost nothing, so a repeat run within the cache TTL is free; retries cost
    one send each. ``per_page`` (up to 100) lowers the number of pages.

    Args:
        client: The client to send the requests with. Its cache, retry policy
            and ``on_request`` callback apply to every request.
        since: An aware ``datetime``. A ``date`` means the start of that day in
            UTC. A naive ``datetime`` raises ``ValueError``.
        max_requests: Cap on HTTP sends, the unit the rate limit counts, or
            ``None`` (the default) for no cap. Every attempt is a send, retries
            included, and a cache hit costs none. The cap is checked before each
            search page and each lookup: once the sends so far reach it, the
            scan stops and returns what it found with ``complete=False``. A
            request already started may still retry, so the sends can exceed the
            cap by up to ``client.max_retries``; with ``max_retries=0`` the cap is
            exact. Sends are counted from the ``RequestEvent``s this call's
            requests emit, which ``on_request`` still receives. Must be at
            least 1.
        **search_params: Other search parameters, such as ``artist`` or
            ``format``, passed to ``client.search()``. ``type`` may only be
            ``"release"``; ``sort``, ``sort_order`` and ``page`` belong to the
            scan. ``None`` values are dropped, as ``search()`` does.

    Returns:
        The releases added on or after *since*, newest first, and whether the
        scan ran to its end.

    Raises:
        ValueError: An argument is invalid, before any request is sent.
        TypeError: *since* is neither a ``date`` nor a ``datetime``, before any
            request is sent.
        DiscogsError: The search results are not sorted by ``date_added``,
            newest first. Errors from the requests themselves propagate as
            they do from the methods sending them.
    """
    cutoff = _cutoff(since)
    if max_requests is not None and max_requests < 1:
        raise ValueError(f"max_requests must be at least 1, got {max_requests}")
    params = {k: v for k, v in search_params.items() if v is not None}
    if params.get("type", "release") != "release":
        raise ValueError(
            f"releases_added_since() searches releases only; got type={params['type']!r}"
        )
    owned = [name for name in _OWNED_PARAMS if name in params]
    if owned:
        raise ValueError(
            f"releases_added_since() sets {', '.join(owned)} itself; remove it from the search parameters"
        )
    params.update(type="release", sort="date_added", sort_order="desc")
    found: list[Release] = []
    seen: set[int] = set()
    # The last release with a date_added: under the assumed sort, the oldest yet.
    previous: tuple[Release, datetime] | None = None
    page = 1
    with client._collect_events() as events:
        while True:
            if _capped(events, max_requests):
                return ReleasesAddedSince(found, complete=False)
            result = client.search(**params, page=page).fetch()
            for item in result.items:
                if item.id in seen:
                    continue
                if _capped(events, max_requests):
                    return ReleasesAddedSince(found, complete=False)
                release = client.releases.get(item.id)._resolve()
                seen.add(item.id)
                added = release.date_added
                if added is None:
                    continue
                if previous is not None and added > previous[1]:
                    raise _unsorted(release, added, *previous)
                previous = (release, added)
                if added < cutoff:
                    return ReleasesAddedSince(found, complete=True)
                found.append(release)
            if not result.items or not result.urls.get("next"):
                return ReleasesAddedSince(found, complete=True)
            page += 1


def _cutoff(since: date | datetime) -> datetime:
    """*since* as an aware ``datetime``; a ``date`` is midnight UTC."""
    if isinstance(since, datetime):
        if since.utcoffset() is None:
            raise ValueError(
                "since must be timezone-aware; pass a date for midnight UTC"
            )
        return since
    if isinstance(since, date):
        return datetime.combine(since, time.min, tzinfo=timezone.utc)
    raise TypeError(f"since must be a date or datetime, got {type(since).__name__}")


def _capped(events: list[RequestEvent], max_requests: int | None) -> bool:
    """Whether the sends behind *events* have reached *max_requests*."""
    if max_requests is None:
        return False
    # A loop rather than sum() over a generator, which ast.unparse wraps in
    # parentheses that ruff then rejects in the generated sync module.
    sends = 0
    for event in events:
        if event.source == "network":
            sends += event.attempts
    return sends >= max_requests


def _unsorted(
    release: Release, added: datetime, previous: Release, previous_added: datetime
) -> DiscogsError:
    return DiscogsError(
        f"Search results are not sorted by date_added, newest first: release {release.id} (added {added.isoformat()}) comes after release {previous.id} (added {previous_added.isoformat()}). releases_added_since() depends on this undocumented sort order of /database/search, so it cannot return a trustworthy result."
    )
