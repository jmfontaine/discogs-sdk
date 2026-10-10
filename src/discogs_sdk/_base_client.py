from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import math
import os
import random
import time
import urllib.parse
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Literal, NoReturn

import httpx2

from discogs_sdk._events import RateLimit, RequestEvent
from discogs_sdk._exceptions import (
    AuthenticationError,
    DiscogsAPIError,
    DiscogsError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)

logger = logging.getLogger("discogs_sdk")

DEFAULT_BASE_URL = "https://api.discogs.com"
DEFAULT_TIMEOUT = 30.0
DEFAULT_CACHE_TTL = 3600.0
# Statuses worth retrying when replaying the request cannot duplicate an effect.
_RETRY_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD"})
# Transport failures a fresh attempt can cure. RemoteProtocolError is what a pooled
# keep-alive connection raises once the server has closed it. Every other
# RequestError (e.g. LocalProtocolError, UnsupportedProtocol, ProxyError,
# DecodingError, TooManyRedirects) fails the same way on every attempt.
_TRANSIENT_TRANSPORT_ERRORS: tuple[type[httpx2.RequestError], ...] = (
    httpx2.NetworkError,
    httpx2.TimeoutException,
    httpx2.RemoteProtocolError,
)
# Transport failures that prove no request reached the server.
_PRE_SEND_TRANSPORT_ERRORS: tuple[type[httpx2.RequestError], ...] = (
    httpx2.ConnectError,
    httpx2.ConnectTimeout,
    httpx2.PoolTimeout,
)
# Longest server-requested wait the client sleeps through before retrying. A valid
# Retry-After above it surfaces the response instead: retrying sooner would ignore
# the server, and parking the caller longer is the caller's call. Matches the
# backoff cap.
MAX_RETRY_AFTER = 60.0
# Longest message an API error carries in ``args[0]`` and so in ``str(exc)``, which
# logs and tracebacks print whole. ``response_body`` keeps the full payload.
MAX_ERROR_MESSAGE_LENGTH = 500
_DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443}


def _url_origin(url: urllib.parse.SplitResult) -> tuple[str, str, int | None]:
    """Scheme, lower-cased host and effective port of *url*.

    Raises ``ValueError`` for a non-numeric or out-of-range port.
    """
    port = url.port
    if port is None:
        port = _DEFAULT_PORTS.get(url.scheme)
    return url.scheme, url.hostname or "", port


def _remove_dot_segments(path: str) -> str:
    """Drop ``.`` and ``..`` path segments (RFC 3986 §5.2.4), as httpx2 does on send."""
    output: list[str] = []
    for segment in path.split("/"):
        if segment == "..":
            if output and output != [""]:
                output.pop()
        elif segment != ".":
            output.append(segment)
    return "/".join(output)


_DEFAULT_ORIGIN = _url_origin(urllib.parse.urlsplit(DEFAULT_BASE_URL))


def may_retry_status(method: str, status_code: int) -> bool:
    """Whether *status_code* allows another attempt for *method*.

    Any status means the server was reached, so a mutation is never replayed:
    the change may already be committed. ``Retry-After`` still reaches callers
    through ``RateLimitError``.
    """
    return method.upper() in _SAFE_METHODS and status_code in _RETRY_STATUSES


def may_retry_transport_error(method: str, exc: httpx2.RequestError) -> bool:
    """Whether *exc* allows another attempt for *method*.

    Reads retry transient failures: network errors, timeouts and a connection the
    server dropped (``RemoteProtocolError``). Deterministic failures (local protocol
    violations, unsupported schemes, proxy errors, undecodable bodies, redirect
    loops) are never retried. Mutations retry only failures that prove no request
    reached the server: the connection was never established or never acquired. A
    read, write or ambiguous timeout, or a dropped connection, may follow a
    committed change.
    """
    if method.upper() in _SAFE_METHODS:
        return isinstance(exc, _TRANSIENT_TRANSPORT_ERRORS)
    return isinstance(exc, _PRE_SEND_TRANSPORT_ERRORS)


def parse_retry_after(value: str | None) -> float | None:
    """Seconds to wait per a ``Retry-After`` header, or None when it is unusable.

    Accepts a finite, non-negative number of seconds or an HTTP-date (RFC 9110),
    the latter measured from now and floored at 0. Anything else yields None.
    """
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        pass
    else:
        return seconds if math.isfinite(seconds) and seconds >= 0 else None
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):  # Overflow: huge year or zone
        return None
    if when.tzinfo is None:  # "-0000" zone: RFC 5322 treats it as UTC
        when = when.replace(tzinfo=timezone.utc)
    return max((when - datetime.now(timezone.utc)).total_seconds(), 0.0)


def _error_message(body: dict[str, Any] | str) -> str:
    """Bounded summary of an error body for the exception message.

    A dict body's ``message`` is used only when it is a non-empty string; otherwise
    the whole dict is rendered. Anything longer than ``MAX_ERROR_MESSAGE_LENGTH`` is
    cut to that length, ending in ``…``.
    """
    if isinstance(body, dict):
        message = body.get("message")
        if not isinstance(message, str) or not message:
            message = str(body)
    else:
        message = body
    if len(message) > MAX_ERROR_MESSAGE_LENGTH:
        message = message[: MAX_ERROR_MESSAGE_LENGTH - 1] + "…"
    return message


try:
    _SDK_VERSION = importlib.metadata.version("discogs-sdk")
except (
    importlib.metadata.PackageNotFoundError
):  # pragma: no cover — package is always installed when tests run
    _SDK_VERSION = "0.0.0"

USER_AGENT = f"discogs-sdk/{_SDK_VERSION} +https://github.com/jmfontaine/discogs-sdk"

MediaType = Literal["discogs", "html", "plaintext"]
AuthMode = Literal["none", "token", "oauth", "consumer"]
_AUTH_MODE_LABELS: dict[str, str] = {
    "none": "none (unauthenticated)",
    "token": "personal access token",
    "oauth": "OAuth 1.0a",
    "consumer": "consumer key/secret",
}

_CACHE_KEY_VERSION = "v1"
_KEY_SEPARATOR = "\x1f"


def _digest(*parts: str | None) -> str:
    """Non-reversible fingerprint of credential material, safe to store in a key.

    The preimage is a JSON array, so no credential can forge the boundary between
    two parts: nothing a caller passes can make distinct tuples share a digest.
    """
    preimage = json.dumps([part or "" for part in parts], separators=(",", ":"))
    return hashlib.sha256(preimage.encode()).hexdigest()[:32]


def _raise_incomplete_credentials(mode: str, **credentials: str | None) -> NoReturn:
    missing = sorted(name for name, value in credentials.items() if not value)
    raise ValueError(
        f"{mode} authentication was selected but {', '.join(missing)} "
        f"{'is' if len(missing) == 1 else 'are'} missing. Pass the missing "
        "value(s) to the constructor or set the matching DISCOGS_* "
        "environment variable(s)."
    )


def _generate_nonce() -> str:
    return os.urandom(16).hex()


def build_oauth_header(
    *,
    consumer_key: str,
    consumer_secret: str,
    token: str = "",
    token_secret: str = "",
    verifier: str = "",
    callback: str = "",
) -> str:
    """Build an OAuth 1.0a Authorization header using PLAINTEXT signatures."""
    # RFC 5849 §3.4.4: each secret is encoded before the two are joined with "&";
    # the joined value is then encoded again like every other header parameter.
    signature = (
        f"{urllib.parse.quote(consumer_secret, safe='')}"
        f"&{urllib.parse.quote(token_secret, safe='')}"
    )
    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": _generate_nonce(),
        "oauth_signature": signature,
        "oauth_signature_method": "PLAINTEXT",
        "oauth_timestamp": str(int(time.time())),
    }
    if token:
        params["oauth_token"] = token
    if verifier:
        params["oauth_verifier"] = verifier
    if callback:
        params["oauth_callback"] = callback
    header_parts = ", ".join(
        f'{k}="{urllib.parse.quote(v, safe="")}"' for k, v in params.items()
    )
    return f"OAuth {header_parts}"


class BaseClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        consumer_key: str | None = None,
        consumer_secret: str | None = None,
        access_token: str | None = None,
        access_token_secret: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        user_agent: str | None = None,
        media_type: MediaType = "discogs",
        on_request: Callable[[RequestEvent], None] | None = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self.base_url: str = base_url.rstrip("/")
        self.timeout: float = timeout
        self.max_retries: int = max_retries
        self._user_agent: str = user_agent if user_agent else USER_AGENT
        self._media_type: MediaType = media_type
        self._on_request = on_request
        self._ratelimit: RateLimit | None = None

        self._auth_mode: AuthMode = self._select_auth_mode(
            token=token,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )
        logger.debug("Auth: %s", _AUTH_MODE_LABELS[self._auth_mode])
        self._auth_namespace: str = self._build_auth_namespace()

    @property
    def ratelimit(self) -> RateLimit | None:
        """Rate limit reported by the most recent live response, or ``None``.

        Only network responses carrying all three ``X-Discogs-Ratelimit*`` headers
        update it; cache hits and responses without the headers leave the last
        known value in place.
        """
        return self._ratelimit

    def _observe(self, event: RequestEvent) -> None:
        """Record *event*'s rate limit and hand it to the ``on_request`` callback."""
        if event.ratelimit is not None:
            self._ratelimit = event.ratelimit
        if self._on_request is not None:
            self._on_request(event)

    def _build_auth_namespace(self) -> str:
        """Stable, non-reversible identity for cache partitioning.

        Derived only from the selected mode's long-lived credentials, so it stays
        identical across OAuth requests with fresh nonces and across restarts.
        """
        match self._auth_mode:
            case "token":
                return f"token:{_digest(self._token)}"
            case "consumer":
                return f"consumer:{_digest(self._consumer_key, self._consumer_secret)}"
            case "oauth":
                return f"oauth:{_digest(*(self._oauth_credentials or ()))}"
            case _:
                return "anonymous"

    def _build_cache_key(self, method: str, url: str, accept: str) -> str:
        """Version-tagged key partitioned by identity and response representation.

        The unit separator cannot appear in any component, so distinct inputs can
        never produce the same key. Bumping the version retires older entries
        instead of letting them serve as fallback hits.
        """
        return _KEY_SEPARATOR.join(
            (_CACHE_KEY_VERSION, method.upper(), url, accept, self._auth_namespace)
        )

    def _select_auth_mode(
        self,
        *,
        token: str | None,
        consumer_key: str | None,
        consumer_secret: str | None,
        access_token: str | None,
        access_token_secret: str | None,
    ) -> AuthMode:
        """Pick exactly one authentication mode and bind only that mode's credentials.

        Precedence, documented in the README: an explicit personal token wins over
        every environment credential; explicit OAuth access-token credentials select
        OAuth; explicit consumer credentials select consumer auth without borrowing
        environment access tokens; otherwise the environment resolves the mode.
        """
        env = os.environ.get
        self._token: str | None = None
        self._consumer_key: str | None = None
        self._consumer_secret: str | None = None
        self._access_token: str | None = None
        self._access_token_secret: str | None = None
        self._oauth_credentials: tuple[str, str, str, str] | None = None

        if token:
            self._token = token
            return "token"

        if access_token or access_token_secret:
            # Explicitly selected OAuth. Missing halves may come from the matching
            # environment variables, but an unrelated env token must not take over.
            key = consumer_key or env("DISCOGS_CONSUMER_KEY")
            secret = consumer_secret or env("DISCOGS_CONSUMER_SECRET")
            oauth_token = access_token or env("DISCOGS_ACCESS_TOKEN")
            oauth_secret = access_token_secret or env("DISCOGS_ACCESS_TOKEN_SECRET")
            if not (key and secret and oauth_token and oauth_secret):
                _raise_incomplete_credentials(
                    "OAuth",
                    consumer_key=key,
                    consumer_secret=secret,
                    access_token=oauth_token,
                    access_token_secret=oauth_secret,
                )
            self._consumer_key, self._consumer_secret = key, secret
            self._access_token, self._access_token_secret = oauth_token, oauth_secret
            self._oauth_credentials = (key, secret, oauth_token, oauth_secret)
            return "oauth"

        if consumer_key or consumer_secret:
            # Explicitly selected consumer auth. Never borrow environment access
            # tokens here; that would silently upgrade to a different identity.
            key = consumer_key or env("DISCOGS_CONSUMER_KEY")
            secret = consumer_secret or env("DISCOGS_CONSUMER_SECRET")
            if not (key and secret):
                _raise_incomplete_credentials(
                    "Consumer key/secret", consumer_key=key, consumer_secret=secret
                )
            self._consumer_key, self._consumer_secret = key, secret
            return "consumer"

        # Nothing explicit selected a mode: fall back to the environment.
        env_token = env("DISCOGS_TOKEN")
        if env_token:
            self._token = env_token
            return "token"

        key, secret = env("DISCOGS_CONSUMER_KEY"), env("DISCOGS_CONSUMER_SECRET")
        oauth_token, oauth_secret = (
            env("DISCOGS_ACCESS_TOKEN"),
            env("DISCOGS_ACCESS_TOKEN_SECRET"),
        )
        if key and secret and oauth_token and oauth_secret:
            self._consumer_key, self._consumer_secret = key, secret
            self._access_token, self._access_token_secret = oauth_token, oauth_secret
            self._oauth_credentials = (key, secret, oauth_token, oauth_secret)
            return "oauth"

        if key and secret:
            self._consumer_key, self._consumer_secret = key, secret
            return "consumer"

        return "none"

    @property
    def _uses_oauth(self) -> bool:
        return self._auth_mode == "oauth"

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": self._user_agent,
            "Accept": f"application/vnd.discogs.v2.{self._media_type}+json",
        }
        if self._auth_mode == "token":
            headers["Authorization"] = f"Discogs token={self._token}"
        elif self._auth_mode == "consumer":
            headers["Authorization"] = (
                f"Discogs key={self._consumer_key}, secret={self._consumer_secret}"
            )
        # OAuth headers are per-request (need fresh nonce/timestamp),
        # so they are added in _build_oauth_header_for_request() instead.
        return headers

    def _build_oauth_header_for_request(self) -> str:
        credentials = self._oauth_credentials
        if credentials is None:
            raise ValueError("OAuth is not the selected authentication mode")
        consumer_key, consumer_secret, token, token_secret = credentials
        return build_oauth_header(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            token=token,
            token_secret=token_secret,
        )

    def _build_url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _resolve_next_url(self, next_url: str) -> str:
        """Turn a pagination ``next`` link from a response body into the URL to request.

        Discogs emits absolute links on its own origin even when ``base_url`` points
        at a proxy, so a link is trusted on that origin or the configured one, and is
        always rebased onto ``base_url``. Any other origin raises before a request,
        and the credentials it would carry, leaves the process.
        """
        base = urllib.parse.urlsplit(self.base_url)
        base_origin = _url_origin(base)
        try:
            link = urllib.parse.urlsplit(next_url)
            origin = _url_origin(link)
        except ValueError:  # Unbalanced IPv6 brackets, unparsable port
            raise DiscogsError("Refusing to follow malformed pagination link") from None
        if origin not in (base_origin, _DEFAULT_ORIGIN):
            if not link.netloc:
                raise DiscogsError(
                    "Refusing to follow pagination link without an origin"
                )
            # Drop any userinfo: the message names where the link points, nothing more.
            host = link.netloc.rpartition("@")[2]
            raise DiscogsError(
                f"Refusing to follow pagination link to untrusted origin "
                f"{link.scheme}://{host}"
            )
        # Resolved first, as httpx2 would after concatenation, so `..` cannot climb
        # out of the base path.
        path = _remove_dot_segments(link.path)
        # A rewriting proxy hands back links that already carry the base path.
        if origin == base_origin and (
            path == base.path or path.startswith(f"{base.path}/")
        ):
            path = path[len(base.path) :]
        query = f"?{link.query}" if link.query else ""
        return f"{self.base_url}{path}{query}"

    def _retry_delay(self, attempt: int, retry_after: str | None = None) -> float:
        server_wait = parse_retry_after(retry_after)
        if server_wait is not None:
            return server_wait
        # Exponential backoff (2^attempt) capped at 60s, plus random jitter to
        # avoid thundering herd
        return min(2**attempt, 60) + random.random()

    def _raise_for_response(self, response: httpx2.Response) -> None:
        """Single HTTP-error boundary, applied before any endpoint JSON parsing.

        A failing response is decoded as JSON when possible; otherwise its text is
        preserved verbatim, including an empty body, so gateway HTML and blank
        error pages surface as ``DiscogsAPIError`` rather than a JSON decode error.
        """
        if response.status_code < 400:
            return

        body: dict[str, Any] | str
        try:
            decoded = response.json()
        except ValueError:
            body = response.text
        else:
            body = decoded if isinstance(decoded, dict) else response.text

        self._maybe_raise(
            response.status_code,
            body,
            retry_after=response.headers.get("Retry-After"),
            ratelimit=RateLimit.from_headers(response.headers),
        )

    def _maybe_raise(
        self,
        status_code: int,
        body: dict[str, Any] | str,
        *,
        retry_after: str | None = None,
        ratelimit: RateLimit | None = None,
    ) -> None:
        if status_code < 400:
            return

        message = _error_message(body)

        error_cls: type[DiscogsAPIError]
        match status_code:
            case 401:
                error_cls = AuthenticationError
            case 403:
                error_cls = ForbiddenError
            case 404:
                error_cls = NotFoundError
            case 422:
                error_cls = ValidationError
            case 429:
                raise RateLimitError(
                    message,
                    status_code=429,
                    response_body=body,
                    retry_after=retry_after,
                    ratelimit=ratelimit,
                )
            case _:
                error_cls = DiscogsAPIError

        raise error_cls(
            message,
            status_code=status_code,
            response_body=body,
        )
