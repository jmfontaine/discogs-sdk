from __future__ import annotations

from typing import Any

from discogs_sdk._events import RateLimit


def _rebuild(
    cls: type[BaseException], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> BaseException:
    """Recreate an SDK exception from its constructor arguments.

    Module-level so pickle can reference it; ``copy`` and ``deepcopy`` use it too.
    """
    return cls(*args, **kwargs)


def _reduce(
    exc: BaseException,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    fields: tuple[str, ...],
) -> tuple[Any, ...]:
    """Build a ``__reduce__`` value that calls the constructor explicitly.

    ``fields`` names the attributes the constructor sets; everything else in
    ``__dict__`` (``__notes__``, caller-added attributes) becomes the state that
    ``BaseException.__setstate__`` restores, and never reaches the constructor.
    """
    state = {key: value for key, value in vars(exc).items() if key not in fields}
    return _rebuild, (type(exc), args, kwargs), state


class DiscogsError(Exception):
    """Base exception for all Discogs SDK errors.

    Every SDK exception survives ``pickle``, ``copy.copy`` and ``copy.deepcopy``,
    so it can cross a process boundary. ``__cause__``, ``__context__`` and
    ``__traceback__`` are dropped, as with any pickled exception.
    """


class DiscogsConnectionError(DiscogsError):
    """Requests that ended without a usable response.

    DNS failures, timeouts, refused or dropped connections, proxy errors, undecodable
    bodies and redirect loops. ``__cause__`` holds the underlying ``httpx2`` error.
    """


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

    def __reduce__(self) -> tuple[Any, ...]:
        return _reduce(self, (self.method, self.url), {}, ("method", "url"))


class DiscogsAPIError(DiscogsError):
    """HTTP error returned by the Discogs API.

    ``str(exc)`` is a bounded summary, ``"<status_code>: <message>"``: the message is
    the body's ``message`` when that is a non-empty string, otherwise the body
    itself, cut to 500 characters. ``response_body`` holds the full payload.

    Attributes:
        status_code: HTTP status of the response.
        response_body: The JSON object the response decoded to, otherwise its
            raw text, unabridged.
    """

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

    def __reduce__(self) -> tuple[Any, ...]:
        # args[0] is the raw message; str(self) would add a second status prefix.
        kwargs = {"status_code": self.status_code, "response_body": self.response_body}
        return _reduce(self, (self.args[0],), kwargs, tuple(kwargs))


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

    def __reduce__(self) -> tuple[Any, ...]:
        kwargs = {
            "status_code": self.status_code,
            "response_body": self.response_body,
            "retry_after": self.retry_after,
            "ratelimit": self.ratelimit,
        }
        return _reduce(self, (self.args[0],), kwargs, tuple(kwargs))


class ValidationError(DiscogsAPIError):
    """422 Unprocessable Entity."""
