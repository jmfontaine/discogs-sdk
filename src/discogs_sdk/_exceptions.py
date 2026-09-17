from __future__ import annotations

from typing import Any

from discogs_sdk._events import RateLimit


class DiscogsError(Exception):
    """Base exception for all Discogs SDK errors."""


class DiscogsConnectionError(DiscogsError):
    """Network-level errors (DNS, timeout, connection refused)."""


class CacheMissError(DiscogsError):
    """Raised inside ``cache_only()`` when a request cannot be served from cache.

    Attributes:
        method: Upper-case HTTP method of the request.
        url: Fully resolved request URL.
    """

    def __init__(self, method: str, url: str) -> None:
        super().__init__(f"Not cached: {method} {url}")
        self.method = method
        self.url = url


class DiscogsAPIError(DiscogsError):
    """HTTP error returned by the Discogs API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        response_body: dict[str, Any] | str,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

    def __str__(self) -> str:
        return f"{self.status_code}: {super().__str__()}"


class AuthenticationError(DiscogsAPIError):
    """401 Unauthorized."""


class ForbiddenError(DiscogsAPIError):
    """403 Forbidden."""


class NotFoundError(DiscogsAPIError):
    """404 Not Found."""


class RateLimitError(DiscogsAPIError):
    """429 Too Many Requests.

    Attributes:
        retry_after: Raw ``Retry-After`` header value, when present.
        ratelimit: Rate-limit headers carried by the 429 itself, when present.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        response_body: dict[str, Any] | str,
        retry_after: str | None = None,
        ratelimit: RateLimit | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, response_body=response_body)
        self.retry_after = retry_after
        self.ratelimit = ratelimit


class ValidationError(DiscogsAPIError):
    """422 Unprocessable Entity."""
