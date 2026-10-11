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

    The SDK always sets ``method`` and ``url``, so an error raised mid-pagination or
    inside a loop names the request that failed. All three request attributes are
    ``None`` on an instance constructed without them.

    Attributes:
        status_code: HTTP status of the response.
        response_body: The JSON object the response decoded to, otherwise its
            raw text, unabridged.
        method: Upper-case HTTP method of the failed request.
        url: Fully resolved URL of the failed request, query string included (the
            ``RequestEvent.url`` value). For a paginated listing, the page that
            failed.
        ratelimit: ``RateLimit`` from the failing response's
            ``X-Discogs-Ratelimit*`` headers, whatever its status; ``None`` unless
            all three are present.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        response_body: dict[str, Any] | str,
        method: str | None = None,
        url: str | None = None,
        ratelimit: RateLimit | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.method = method
        self.url = url
        self.ratelimit = ratelimit

    def __str__(self) -> str:
        return f"{self.status_code}: {super().__str__()}"

    def _init_kwargs(self) -> dict[str, Any]:
        """Keyword arguments that rebuild this exception through ``__init__``."""
        return {
            "status_code": self.status_code,
            "response_body": self.response_body,
            "method": self.method,
            "url": self.url,
            "ratelimit": self.ratelimit,
        }

    def __reduce__(self) -> tuple[Any, ...]:
        # args[0] is the raw message; str(self) would add a second status prefix.
        kwargs = self._init_kwargs()
        return _reduce(self, (self.args[0],), kwargs, tuple(kwargs))


class AuthenticationError(DiscogsAPIError):
    """401 Unauthorized."""


class ForbiddenError(DiscogsAPIError):
    """403 Forbidden."""


class NotFoundError(DiscogsAPIError):
    """404 Not Found."""


class RateLimitError(DiscogsAPIError):
    """429 Too Many Requests.

    ``ratelimit``, inherited like ``method`` and ``url``, holds the 429's own
    ``X-Discogs-Ratelimit*`` headers when present.

    Attributes:
        retry_after: Raw ``Retry-After`` header value, when present.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        response_body: dict[str, Any] | str,
        retry_after: str | None = None,
        method: str | None = None,
        url: str | None = None,
        ratelimit: RateLimit | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            response_body=response_body,
            method=method,
            url=url,
            ratelimit=ratelimit,
        )
        self.retry_after = retry_after

    def _init_kwargs(self) -> dict[str, Any]:
        return {**super()._init_kwargs(), "retry_after": self.retry_after}


class ValidationError(DiscogsAPIError):
    """422 Unprocessable Entity."""
