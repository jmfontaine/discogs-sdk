"""Structured request observability: rate-limit headers and per-request events.

Stdlib-only so ``_exceptions`` can import it without a cycle.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

_LIMIT = "x-discogs-ratelimit"
_USED = "x-discogs-ratelimit-used"
_REMAINING = "x-discogs-ratelimit-remaining"


@dataclass(frozen=True, slots=True)
class RateLimit:
    """Discogs rate-limit headers from one live response.

    Attributes:
        limit: Requests allowed per window (``X-Discogs-Ratelimit``).
        used: Requests made in the current window (``X-Discogs-Ratelimit-Used``).
        remaining: Requests left in the current window
            (``X-Discogs-Ratelimit-Remaining``).
    """

    limit: int
    used: int
    remaining: int

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> RateLimit | None:
        """Parse the three headers; ``None`` unless all are present and integers.

        Header names are matched case-insensitively.
        """
        lowered = {k.lower(): v for k, v in headers.items()}
        try:
            return cls(
                int(lowered[_LIMIT]), int(lowered[_USED]), int(lowered[_REMAINING])
            )
        except (KeyError, ValueError):
            return None


@dataclass(frozen=True, slots=True)
class RequestEvent:
    """One logical request as seen by the client; emitted once per call.

    Attributes:
        method: Upper-case HTTP method.
        url: Fully resolved request URL, query string included.
        status_code: HTTP status of the response that ended the call.
        source: ``"network"`` for a live response, ``"cache"`` for a cache hit.
        elapsed_ms: Duration of the final network attempt, or of the cache lookup.
        attempts: Network attempts made (``1`` means no retry); ``0`` on a cache
            hit.
        stored: Whether this call wrote the response to the cache.
        ratelimit: Rate limit reported by the response; always ``None`` for a
            cache hit.
    """

    method: str
    url: str
    status_code: int
    source: Literal["network", "cache"]
    elapsed_ms: float
    attempts: int
    stored: bool
    ratelimit: RateLimit | None
