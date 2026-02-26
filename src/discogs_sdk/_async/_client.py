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
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any

from typing_extensions import Self

import httpx

from discogs_sdk._base_client import (
    DEFAULT_BASE_URL,
    DEFAULT_CACHE_TTL,
    DEFAULT_TIMEOUT,
    BaseClient,
    MediaType,
    _RETRY_STATUSES,
)
from discogs_sdk._cache import MemoryCache, ResponseCache, SQLiteCache
from discogs_sdk._exceptions import DiscogsConnectionError
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

if TYPE_CHECKING:
    from discogs_sdk._async._paginator import AsyncPage
    from discogs_sdk.models.search import SearchResult

logger = logging.getLogger("discogs_sdk")

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
        http_client: httpx.AsyncClient | None = None,
        user_agent: str | None = None,
        media_type: MediaType = "discogs",
    ) -> None:
        """Create an async Discogs client.

        Args:
            token: Personal access token from https://www.discogs.com/settings/developers.
            consumer_key: OAuth consumer key for app-level auth.
            consumer_secret: OAuth consumer secret for app-level auth.
            access_token: OAuth access token for user-level auth.
            access_token_secret: OAuth access token secret for user-level auth.
            base_url: API base URL.
            timeout: Request timeout in seconds.
            max_retries: Max retries on 429/5xx/connection errors.
            cache: Enable response caching. Pass ``True`` for the built-in
                backend, or a ``ResponseCache`` instance for a custom one.
            cache_ttl: Cache time-to-live in seconds (default 1 hour).
                Ignored when *cache* is a ``ResponseCache`` instance or ``False``.
            cache_dir: Directory for the cache database. When provided, uses
                SQLite for persistence; otherwise caches in memory only.
                Ignored when *cache* is a ``ResponseCache`` instance or ``False``.
            http_client: Custom ``httpx.AsyncClient`` to use instead of creating one.
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
            self._http_client = http_client
            self._owns_client = False
        else:
            self._http_client = httpx.AsyncClient(
                headers=self._build_headers(),
                timeout=self.timeout,
            )
            self._owns_client = True

        self._cache: ResponseCache | None = None
        if isinstance(cache, ResponseCache):
            self._cache = cache
        elif cache:
            self._cache = (
                SQLiteCache(ttl=cache_ttl, cache_dir=Path(cache_dir)) if cache_dir else MemoryCache(ttl=cache_ttl)
            )
        self._cache_enabled: bool = True

    async def _send(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> httpx.Response:
        kwargs: dict[str, Any] = {}
        if json is not None:
            kwargs["json"] = json
        if params is not None:
            kwargs["params"] = params
        if files is not None:
            kwargs["files"] = files
        if self._uses_oauth:
            kwargs.setdefault("headers", {})["Authorization"] = self._build_oauth_header_for_request()

        # Build the full URL for cache key before httpx resolves params.
        use_cache = self._cache is not None and self._cache_enabled and method.upper() in _CACHEABLE_METHODS
        cache_key = ""
        if use_cache:
            # httpx merges params into the URL, so we need to build the key
            # the same way to get consistent cache hits.
            req = self._http_client.build_request(method, url, **kwargs)
            cache_key = f"{method.upper()}:{req.url}"

            cached = self._cache.get(cache_key)  # type: ignore[union-attr]
            if cached is not None:
                status, headers, body = cached
                logger.debug("Cache hit: %s %s", method, url)
                return httpx.Response(status_code=status, headers=headers, content=body)

        for attempt in range(self.max_retries + 1):
            logger.debug("HTTP request: %s %s", method, url)
            t0 = time.monotonic()  # Unaffected by system clock adjustments (NTP, DST)
            try:
                response = await self._http_client.request(method, url, **kwargs)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                elapsed_ms = (time.monotonic() - t0) * 1000
                if attempt == self.max_retries:
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

            if response.status_code not in _RETRY_STATUSES or attempt == self.max_retries:
                if use_cache and 200 <= response.status_code < 300:
                    assert self._cache is not None  # narrowed by use_cache
                    # response.content is already decompressed by httpx, so strip
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
            """Context manager that temporarily disables the response cache."""
            self._cache_enabled = False
            try:
                yield self
            finally:
                self._cache_enabled = True
    else:

        @contextmanager
        def no_cache(self) -> Generator[Self, None, None]:
            """Context manager that temporarily disables the response cache."""
            self._cache_enabled = False
            try:
                yield self
            finally:
                self._cache_enabled = True

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
