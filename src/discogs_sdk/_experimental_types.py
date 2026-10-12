"""Result types for the experimental helpers.

They live outside the generated variants so the sync and async helpers return
the very same classes, and so ``discogs_sdk.experimental`` can annotate both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from discogs_sdk.models.release import Release


@dataclass(frozen=True)
class ReleasesAddedSince:
    """What ``releases_added_since()`` found.

    Attributes:
        releases: Releases added on or after the cutoff, newest first, each
            fetched from ``/releases/{id}`` and carrying its ``date_added``.
        complete: ``True`` when the scan ran to its end: it reached a release
            added before the cutoff, or the results ran out. Even then the result
            is complete only if Discogs sorted the search as assumed. ``False``
            when ``max_requests`` stopped the scan first, so more releases may
            be in the window.
    """

    releases: list[Release]
    complete: bool

    # Declared so hash() names this class; the generated one fails on releases.
    __hash__: ClassVar[None] = None  # type: ignore[assignment]
