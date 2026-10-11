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

    Every call that reaches the request stage emits exactly one, before it
    returns or raises: after a cache hit, after the final network response, after
    the final transport failure (the call then raises ``DiscogsConnectionError``)
    and when ``cache_only()`` refuses the request (the call then raises
    ``CacheMissError``). Retried attempts are folded into ``attempts``, and a
    cache hit rejected because it no longer parses adds no event of its own.

    Attributes:
        method: Upper-case HTTP method.
        url: Fully resolved request URL, query string included.
        status_code: HTTP status of the response that ended the call; ``None``
            when there is none (a transport failure, a refused cache-only
            lookup).
        source: ``"network"`` for a live response or a transport failure,
            ``"cache"`` for a cache hit, ``"miss"`` for a request
            ``cache_only()`` refused.
        elapsed_ms: Duration of the final network attempt, or of the cache
            lookup (``0.0`` for a miss that needed none, such as a non-GET).
        attempts: Network attempts sent, failed ones included (``1`` means no
            retry); ``0`` on a cache hit or a miss.
        stored: Whether this call wrote the response to the cache.
        ratelimit: Rate limit reported by the response; always ``None`` without
            a live response.
        error: Class name of the exception the call raises when there is no
            response to describe it (``"DiscogsConnectionError"``,
            ``"CacheMissError"``); ``None`` otherwise, including for an error
            status, which ``status_code`` already reports.
    """

    method: str
    url: str
    status_code: int | None
    source: Literal["network", "cache", "miss"]
    elapsed_ms: float
    attempts: int
    stored: bool
    ratelimit: RateLimit | None
    error: str | None = None
