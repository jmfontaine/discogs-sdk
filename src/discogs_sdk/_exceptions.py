from __future__ import annotations

from typing import Any


class DiscogsError(Exception):
    """Base exception for all Discogs SDK errors."""


class DiscogsConnectionError(DiscogsError):
    """Network-level errors (DNS, timeout, connection refused)."""


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
    """429 Too Many Requests."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        response_body: dict[str, Any] | str,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, response_body=response_body)
        self.retry_after = retry_after


class ValidationError(DiscogsAPIError):
    """422 Unprocessable Entity."""
