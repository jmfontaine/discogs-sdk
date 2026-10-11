# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx2
from typing_extensions import Self

from discogs_sdk._base_client import (
    DEFAULT_BASE_URL,
    DEFAULT_CACHE_TTL,
    DEFAULT_TIMEOUT,
    MAX_RETRY_AFTER,
    BaseClient,
    MediaType,
    is_json,
    may_retry_status,
    may_retry_transport_error,
    parse_retry_after,
    raise_for_response,
)
from discogs_sdk._cache import MemoryCache, ResponseCache, SQLiteCache
from discogs_sdk._events import RateLimit, RequestEvent
from discogs_sdk._exceptions import CacheMissError, DiscogsConnectionError
from discogs_sdk._sync.resources.artists import Artists
from discogs_sdk._sync.resources.exports import Exports
from discogs_sdk._sync.resources.labels import Labels
from discogs_sdk._sync.resources.lists import Lists
from discogs_sdk._sync.resources.marketplace import Marketplace
from discogs_sdk._sync.resources.masters import Masters
from discogs_sdk._sync.resources.releases import Releases
from discogs_sdk._sync.resources.search import SearchResource
from discogs_sdk._sync.resources.uploads import Uploads
from discogs_sdk._sync.resources.users import UserNamespace, Users

if TYPE_CHECKING:
    from discogs_sdk._sync._paginator import SyncPage
    from discogs_sdk.models.search import SearchResult
logger = logging.getLogger("discogs_sdk")
# Clients whose cache is bypassed in the current execution context. Held as a
# ContextVar so concurrent tasks and threads cannot clobber each other's state.
_CACHE_BYPASS: ContextVar[frozenset[int]] = ContextVar(
    "discogs_sdk_cache_bypass", default=frozenset()
)
# Clients restricted to the cache in the current execution context; same shape.
_CACHE_ONLY: ContextVar[frozenset[int]] = ContextVar(
    "discogs_sdk_cache_only", default=frozenset()
)
_CACHEABLE_METHODS = frozenset({"GET", "HEAD"})
# The only response headers a cache entry keeps. Others (Set-Cookie, rate-limit
# counters) are private or stale on a hit, and the wire-encoding ones would be
# wrong, because httpx2 has already decompressed response.content.
_CACHED_HEADERS = frozenset({"content-type", "etag", "last-modified"})


class Discogs(BaseClient):
    """Client for the Discogs API.

    Use as a context manager to ensure the HTTP client is properly closed::

        with Discogs(token="...") as client:
            release = client.releases.get(352665)
            print(release.title)  # The Downward Spiral
    """

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
        cache: bool | ResponseCache = False,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        cache_dir: str | Path | None = None,
        http_client: httpx2.Client | None = None,
        user_agent: str | None = None,
        media_type: MediaType = "discogs",
        on_request: Callable[[RequestEvent], None] | None = None,
    ) -> None:
        """Create a Discogs client.

        Exactly one authentication mode is selected here and used for every
        request: an explicit *token* wins, then explicit OAuth access-token
        credentials, then explicit consumer credentials, then the ``DISCOGS_*``
        environment variables. An explicitly selected but incomplete credential
        set raises ``ValueError`` rather than falling back to another identity.

        Args:
            token: Personal access token from https://www.discogs.com/settings/developers.
            consumer_key: OAuth consumer key for app-level auth.
            consumer_secret: OAuth consumer secret for app-level auth.
            access_token: OAuth access token for user-level auth.
            access_token_secret: OAuth access token secret for user-level auth.
            base_url: API base URL.
            timeout: Request timeout in seconds.
            max_retries: Max retry attempts, ``>= 0`` (``0`` disables retries;
                a negative value raises ``ValueError``). Reads retry on 429/5xx and on
                network errors and timeouts. Mutations retry only failures that
                prove the request never reached the server, never after an HTTP
                status, so a possibly committed change is never sent twice. A
                ``Retry-After`` is honoured up to 60 seconds; a longer one raises
                the error at once instead of waiting or retrying early.
            cache: Enable response caching. Pass ``True`` for the built-in
                backend, or a ``ResponseCache`` instance for a custom one.
                Entries are partitioned by credential identity and response
                representation, so clients sharing a cache stay isolated.
                The client closes a cache it built from ``True``; an injected
                instance stays yours: ``close()`` never closes it, so close it
                yourself once every client using it is done.
            cache_ttl: Cache time-to-live in seconds (default 1 hour).
                Ignored when *cache* is a ``ResponseCache`` instance or ``False``.
            cache_dir: Directory for the cache database. When provided, uses
                SQLite for persistence; otherwise caches in memory only.
                Ignored when *cache* is a ``ResponseCache`` instance or ``False``.
            http_client: Custom ``httpx2.Client`` to use instead of creating
                one. It keeps its transport configuration and its lifecycle:
                ``close()`` never closes it. SDK credentials, User-Agent and
                media type are applied per request without mutating its defaults,
                and its own auth cannot replace them. With no SDK credentials its
                authentication is preserved and its responses are not cached,
                because the SDK cannot tell whose account they belong to.
            user_agent: Custom User-Agent string. Replaces the default entirely.
                Should follow RFC 1945 product token format for best
                compatibility with Discogs.
            media_type: Response text format. ``"discogs"`` returns Discogs markup,
                ``"html"`` returns HTML, ``"plaintext"`` returns plain text.
            on_request: Called once per request with a ``RequestEvent``: after a
                cache hit, or after the final network response before any error
                is raised. Invoked synchronously from the calling task, so keep
                it cheap and never block in it. Exceptions it raises propagate
                unchanged.
        """
        super().__init__(
            token=token,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            user_agent=user_agent,
            media_type=media_type,
            on_request=on_request,
        )
        if http_client is not None:
            # An injected client owns its transport and lifecycle. SDK headers are
            # applied per request instead, so its defaults are never mutated.
            self._http_client = http_client
            self._owns_client = False
        else:
            self._http_client = httpx2.Client(timeout=self.timeout)
            self._owns_client = True
        self._cache: ResponseCache | None = None
        # Like an injected http_client, an injected cache belongs to the caller and
        # may be shared by other clients, so only a cache built here is closed here.
        self._owns_cache = False
        if isinstance(cache, ResponseCache):
            self._cache = cache
        elif cache:
            self._cache = (
                SQLiteCache(ttl=cache_ttl, cache_dir=Path(cache_dir))
                if cache_dir
                else MemoryCache(ttl=cache_ttl)
            )
            self._owns_cache = True

    def _send(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> httpx2.Response:
        """Send a request through the cache and the retry policy.

        *expect_json* says the caller parses the body as JSON, so a 2xx ``GET``
        body that is not valid JSON is returned but never cached. Pass ``False``
        for an endpoint whose body is not JSON (a CSV download).
        """
        build_kwargs: dict[str, Any] = {}
        if json is not None:
            build_kwargs["json"] = json
        if params is not None:
            build_kwargs["params"] = params
        if files is not None:
            build_kwargs["files"] = files
        # Per-request headers win over an injected client's defaults, so SDK
        # credentials and media type always describe the request we asked for.
        headers = self._build_headers()
        build_kwargs["headers"] = headers
        # build_request() takes no auth, so it only ever sees build_kwargs.
        kwargs = dict(build_kwargs)
        if self._auth_mode != "none":
            # Explicit auth=None disables the client's own handler for this
            # request, so it cannot overwrite the Authorization header we set.
            # Omitted entirely when unauthenticated, preserving custom-client auth.
            kwargs["auth"] = None
        # An injected client may carry its own authentication that the SDK
        # cannot identify, so its responses must not be shared across clients.
        use_cache = (
            self._cache is not None
            and id(self) not in _CACHE_BYPASS.get()
            and (method.upper() in _CACHEABLE_METHODS)
            and (self._owns_client or self._auth_mode != "none")
        )
        cache_only = id(self) in _CACHE_ONLY.get()
        cache_key = ""
        if use_cache or cache_only:
            # httpx2 merges params into the URL, so build the request first to key
            # on the fully resolved URL.
            req = self._http_client.build_request(method, url, **build_kwargs)
        if use_cache:
            cache_key = self._build_cache_key(method, str(req.url), headers["Accept"])
            t0 = time.monotonic()
            cached = self._cache.get(cache_key)  # type: ignore[union-attr]
            lookup_ms = (time.monotonic() - t0) * 1000
            if cached is not None:
                status, cached_headers, body = cached
                logger.debug("Cache hit: %s %s", method, url)
                response = httpx2.Response(
                    status_code=status, headers=cached_headers, content=body
                )
                self._observe(
                    RequestEvent(
                        method=method.upper(),
                        url=str(req.url),
                        status_code=status,
                        source="cache",
                        elapsed_ms=lookup_ms,
                        attempts=0,
                        stored=False,
                        ratelimit=None,
                    )
                )
                return response
        if cache_only:
            # Nothing below this line may run: the scope forbids network I/O.
            raise CacheMissError(method.upper(), str(req.url))
        for attempt in range(self.max_retries + 1):
            logger.debug("HTTP request: %s %s", method, url)
            if self._uses_oauth:
                # A nonce is single-use and the timestamp ages with every retry
                # delay, so each attempt is signed afresh just before it is sent.
                # kwargs["headers"] is this same dict.
                headers["Authorization"] = self._build_oauth_header_for_request()
            t0 = time.monotonic()  # Unaffected by system clock adjustments (NTP, DST)
            try:
                response = self._http_client.request(method, url, **kwargs)
            except httpx2.RequestError as exc:
                elapsed_ms = (time.monotonic() - t0) * 1000
                if attempt == self.max_retries or not may_retry_transport_error(
                    method, exc
                ):
                    logger.debug(
                        "HTTP connection error after %.0fms: %s", elapsed_ms, exc
                    )
                    raise DiscogsConnectionError(str(exc)) from exc
                delay = self._retry_delay(attempt)
                logger.info(
                    "Retrying %s %s (attempt %d/%d) after connection error (%.0fms), waiting %.1fs",
                    method,
                    url,
                    attempt + 2,
                    self.max_retries + 1,
                    elapsed_ms,
                    delay,
                )
                time.sleep(delay)
                continue
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.debug(
                "HTTP response: %s %s -> %d (%.0fms)",
                method,
                url,
                response.status_code,
                elapsed_ms,
            )
            retry_after = response.headers.get("Retry-After")
            retryable = (
                may_retry_status(method, response.status_code)
                and attempt < self.max_retries
            )
            if retryable:
                server_wait = parse_retry_after(retry_after)
                if server_wait is not None and server_wait > MAX_RETRY_AFTER:
                    logger.info(
                        "Not retrying %s %s after status %d: Retry-After %.1fs exceeds the %.0fs cap, surfacing the response",
                        method,
                        url,
                        response.status_code,
                        server_wait,
                        MAX_RETRY_AFTER,
                    )
                    retryable = False
            if not retryable:
                stored = False
                # A GET body the caller will parse as JSON is stored only if it is
                # JSON. Only the syntax is checked: JSON of the wrong shape for the
                # caller's model is still cached, because no model is known here,
                # and fails validation on every hit until it expires.
                if (
                    use_cache
                    and 200 <= response.status_code < 300
                    and (
                        not (
                            expect_json
                            and method.upper() == "GET"
                            and (not is_json(response.content))
                        )
                    )
                ):
                    assert self._cache is not None  # narrowed by use_cache
                    cache_headers = {
                        k: v
                        for k, v in response.headers.items()
                        if k.lower() in _CACHED_HEADERS
                    }
                    self._cache.set(
                        cache_key, response.status_code, cache_headers, response.content
                    )
                    stored = True
                # Emitted before the error boundary so the event exists even when
                # the call raises.
                self._observe(
                    RequestEvent(
                        method=method.upper(),
                        url=str(response.request.url),
                        status_code=response.status_code,
                        source="network",
                        elapsed_ms=elapsed_ms,
                        attempts=attempt + 1,
                        stored=stored,
                        ratelimit=RateLimit.from_headers(response.headers),
                    )
                )
                # The retry policy is done deciding: this is the final response,
                # so map failures here, before any endpoint parses the body.
                raise_for_response(response)
                return response
            delay = self._retry_delay(attempt, retry_after=retry_after)
            logger.info(
                "Retrying %s %s (attempt %d/%d) after status %d, waiting %.1fs",
                method,
                url,
                attempt + 2,
                self.max_retries + 1,
                response.status_code,
                delay,
            )
            time.sleep(delay)
        raise AssertionError("unreachable")

    # --- Cache ---

    @contextmanager
    def no_cache(self) -> Generator[Self, None, None]:
        """Bypass the response cache for the current execution context.

        Scopes nest, and the exact previous state is restored on exit, including
        when the block raises. Concurrent tasks and threads each carry their own
        state, so one task leaving a scope never re-enables another's cache.
        """
        token = _CACHE_BYPASS.set(_CACHE_BYPASS.get() | {id(self)})
        try:
            yield self
        finally:
            _CACHE_BYPASS.reset(token)

    @contextmanager
    def cache_only(self) -> Generator[Self, None, None]:
        """Serve only from the response cache for the current execution context.

        A request the cache cannot serve - a miss, an expired entry, a non-GET,
        a disabled cache or an enclosing ``no_cache()`` - raises
        ``CacheMissError`` before any network I/O. Scopes nest and restore
        exactly like ``no_cache()``.
        """
        token = _CACHE_ONLY.set(_CACHE_ONLY.get() | {id(self)})
        try:
            yield self
        finally:
            _CACHE_ONLY.reset(token)

    def clear_cache(self) -> None:
        """Purge all cached responses. No-op when caching is disabled."""
        if self._cache is not None:
            self._cache.clear()

    # --- Database ---

    @cached_property
    def artists(self) -> Artists:
        return Artists(self)

    @cached_property
    def labels(self) -> Labels:
        return Labels(self)

    @cached_property
    def masters(self) -> Masters:
        return Masters(self)

    @cached_property
    def releases(self) -> Releases:
        return Releases(self)

    def search(self, **params: Any) -> SyncPage[SearchResult]:
        """Search the Discogs database.

        Accepts any Discogs search parameter as a keyword argument
        (e.g. ``query``, ``type``, ``title``, ``artist``, ``label``, ``genre``).

        Returns an auto-paging iterator of search results.
        """
        return SearchResource(self)(**params)

    # --- Marketplace ---

    @cached_property
    def marketplace(self) -> Marketplace:
        return Marketplace(self)

    # --- Inventory ---

    @cached_property
    def exports(self) -> Exports:
        return Exports(self)

    @cached_property
    def uploads(self) -> Uploads:
        return Uploads(self)

    # --- Users ---

    @cached_property
    def user(self) -> UserNamespace:
        return UserNamespace(self)

    @cached_property
    def users(self) -> Users:
        return Users(self)

    # --- Lists ---

    @cached_property
    def lists(self) -> Lists:
        return Lists(self)

    # --- Lifecycle ---

    def close(self) -> None:
        """Close the HTTP client and response cache this instance created.

        A custom ``http_client`` or ``ResponseCache`` passed to the constructor
        is left open. The owned cache is closed even when closing the HTTP
        client raises or is interrupted.
        """
        try:
            if self._owns_client:
                self._http_client.close()
        finally:
            if self._owns_cache and self._cache is not None:
                self._cache.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
