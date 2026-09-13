from __future__ import annotations

import logging
import time

if True:  # ASYNC
    import asyncio
    from collections.abc import AsyncGenerator
    from contextlib import asynccontextmanager
else:
    from collections.abc import Generator
    from contextlib import contextmanager
from contextvars import ContextVar
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx2
from typing_extensions import Self

from discogs_sdk._async.resources.artists import Artists
from discogs_sdk._async.resources.exports import Exports
from discogs_sdk._async.resources.labels import Labels
from discogs_sdk._async.resources.lists import Lists
from discogs_sdk._async.resources.marketplace import Marketplace
from discogs_sdk._async.resources.masters import Masters
from discogs_sdk._async.resources.releases import Releases
from discogs_sdk._async.resources.search import SearchResource
from discogs_sdk._async.resources.uploads import Uploads
from discogs_sdk._async.resources.users import UserNamespace, Users
from discogs_sdk._base_client import (
    DEFAULT_BASE_URL,
    DEFAULT_CACHE_TTL,
    DEFAULT_TIMEOUT,
    BaseClient,
    MediaType,
    may_retry_status,
    may_retry_transport_error,
)
from discogs_sdk._cache import MemoryCache, ResponseCache, SQLiteCache
from discogs_sdk._exceptions import DiscogsConnectionError

if TYPE_CHECKING:
    from discogs_sdk._async._paginator import AsyncPage
    from discogs_sdk.models.search import SearchResult

logger = logging.getLogger("discogs_sdk")

# Clients whose cache is bypassed in the current execution context. Held as a
# ContextVar so concurrent tasks and threads cannot clobber each other's state.
_CACHE_BYPASS: ContextVar[frozenset[int]] = ContextVar("discogs_sdk_cache_bypass", default=frozenset())
_CACHEABLE_METHODS = frozenset({"GET", "HEAD"})


class AsyncDiscogs(BaseClient):
    """Async client for the Discogs API.

    Use as a context manager to ensure the HTTP client is properly closed::

        async with AsyncDiscogs(token="...") as client:
            release = await client.releases.get(352665)
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
        http_client: httpx2.AsyncClient | None = None,
        user_agent: str | None = None,
        media_type: MediaType = "discogs",
    ) -> None:
        """Create an async Discogs client.

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
            max_retries: Max retry attempts. Reads retry on 429/5xx and on
                network errors and timeouts. Mutations retry only failures that
                prove the request never reached the server, never after an HTTP
                status, so a possibly committed change is never sent twice.
            cache: Enable response caching. Pass ``True`` for the built-in
                backend, or a ``ResponseCache`` instance for a custom one.
                Entries are partitioned by credential identity and response
                representation, so clients sharing a cache stay isolated.
            cache_ttl: Cache time-to-live in seconds (default 1 hour).
                Ignored when *cache* is a ``ResponseCache`` instance or ``False``.
            cache_dir: Directory for the cache database. When provided, uses
                SQLite for persistence; otherwise caches in memory only.
                Ignored when *cache* is a ``ResponseCache`` instance or ``False``.
            http_client: Custom ``httpx2.AsyncClient`` to use instead of creating
                one. It keeps its transport configuration and its lifecycle:
                ``close()`` never closes it. SDK credentials, User-Agent and
                media type are applied per request without mutating its defaults,
                and its own auth cannot replace them. With no SDK credentials its
                authentication is preserved and its responses are not cached,
                because the SDK cannot tell whose account they belong to.
            user_agent: Custom User-Agent string. Replaces the default entirely.
                Should follow RFC 1945 product token format for best compatibility with Discogs.
            media_type: Response text format. ``"discogs"`` returns Discogs markup,
                ``"html"`` returns HTML, ``"plaintext"`` returns plain text.
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
        )
        if http_client is not None:
            # An injected client owns its transport and lifecycle. SDK headers are
            # applied per request instead, so its defaults are never mutated.
            self._http_client = http_client
            self._owns_client = False
        else:
            self._http_client = httpx2.AsyncClient(timeout=self.timeout)
            self._owns_client = True

        self._cache: ResponseCache | None = None
        if isinstance(cache, ResponseCache):
            self._cache = cache
        elif cache:
            self._cache = (
                SQLiteCache(ttl=cache_ttl, cache_dir=Path(cache_dir)) if cache_dir else MemoryCache(ttl=cache_ttl)
            )

    async def _send(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> httpx2.Response:
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
        if self._uses_oauth:
            headers["Authorization"] = self._build_oauth_header_for_request()
        build_kwargs["headers"] = headers

        # build_request() takes no auth, so it only ever sees build_kwargs.
        kwargs = dict(build_kwargs)
        if self._auth_mode != "none":
            # Explicit auth=None disables the client's own handler for this
            # request, so it cannot overwrite the header we just set. Omitted
            # entirely when unauthenticated, preserving custom-client auth.
            kwargs["auth"] = None

        use_cache = (
            self._cache is not None
            and id(self) not in _CACHE_BYPASS.get()
            and method.upper() in _CACHEABLE_METHODS
            # An injected client may carry its own authentication that the SDK
            # cannot identify, so its responses must not be shared across clients.
            and (self._owns_client or self._auth_mode != "none")
        )
        cache_key = ""
        if use_cache:
            # httpx2 merges params into the URL, so build the request first to key
            # on the fully resolved URL.
            req = self._http_client.build_request(method, url, **build_kwargs)
            cache_key = self._build_cache_key(method, str(req.url), headers["Accept"])

            cached = self._cache.get(cache_key)  # type: ignore[union-attr]
            if cached is not None:
                status, cached_headers, body = cached
                logger.debug("Cache hit: %s %s", method, url)
                return httpx2.Response(status_code=status, headers=cached_headers, content=body)

        for attempt in range(self.max_retries + 1):
            logger.debug("HTTP request: %s %s", method, url)
            t0 = time.monotonic()  # Unaffected by system clock adjustments (NTP, DST)
            try:
                response = await self._http_client.request(method, url, **kwargs)
            except (httpx2.NetworkError, httpx2.TimeoutException) as exc:
                elapsed_ms = (time.monotonic() - t0) * 1000
                if attempt == self.max_retries or not may_retry_transport_error(method, exc):
                    logger.debug("HTTP connection error after %.0fms: %s", elapsed_ms, exc)
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
                if True:  # ASYNC
                    await asyncio.sleep(delay)
                else:
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

            if not may_retry_status(method, response.status_code) or attempt == self.max_retries:
                if use_cache and 200 <= response.status_code < 300:
                    assert self._cache is not None  # narrowed by use_cache
                    # response.content is already decompressed by httpx2, so strip
                    # transport-layer headers that describe the wire encoding.
                    cache_headers = {
                        k: v
                        for k, v in response.headers.items()
                        if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
                    }
                    self._cache.set(
                        cache_key,
                        response.status_code,
                        cache_headers,
                        response.content,
                    )
                # The retry policy is done deciding: this is the final response,
                # so map failures here, before any endpoint parses the body.
                self._raise_for_response(response)
                return response

            delay = self._retry_delay(attempt, retry_after=response.headers.get("Retry-After"))
            logger.info(
                "Retrying %s %s (attempt %d/%d) after status %d, waiting %.1fs",
                method,
                url,
                attempt + 2,
                self.max_retries + 1,
                response.status_code,
                delay,
            )
            if True:  # ASYNC
                await asyncio.sleep(delay)
            else:
                time.sleep(delay)

        return response  # pragma: no cover — unreachable but satisfies type checker

    # --- Cache ---

    if True:  # ASYNC

        @asynccontextmanager
        async def no_cache(self) -> AsyncGenerator[Self, None]:
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
    else:

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

    def search(self, **params: Any) -> AsyncPage[SearchResult]:
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

    async def close(self) -> None:
        """Close the underlying HTTP client.

        Only closes the client if it was created by this instance,
        not if a custom ``http_client`` was passed to the constructor.
        """
        if self._owns_client:
            await self._http_client.aclose()
        if self._cache is not None:
            self._cache.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
