from __future__ import annotations

import logging
import time

if True:  # ASYNC
    import asyncio
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any

from typing_extensions import Self

import httpx

from discogs_sdk._base_client import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, BaseClient, _RETRY_STATUSES, _default_cache_dir
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


class AsyncDiscogs(BaseClient):
    """Async client for the Discogs API.

    Use as a context manager to ensure the HTTP client is properly closed::

        async with AsyncDiscogs(token="...") as client:
            release = await client.releases.get(249504)
            print(release.title)
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
        cache: bool = False,
        cache_dir: str | Path | None = None,
        http_client: httpx.AsyncClient | None = None,
        user_agent: str | None = None,
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
            cache: Enable HTTP caching (requires ``discogs-sdk[cache]``).
            cache_dir: Directory for the cache database. Defaults to
                ``$XDG_CACHE_HOME/discogs-sdk`` or ``~/.cache/discogs-sdk``.
                Ignored when *cache* is ``False``.
            http_client: Custom ``httpx.AsyncClient`` to use instead of creating one.
            user_agent: Custom User-Agent string. Replaces the default entirely.
                Should follow RFC 1945 product token format for best compatibility with Discogs.
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
        )
        if http_client is not None:
            self._http_client = http_client
            self._owns_client = False
        elif cache:
            try:
                from hishel import AsyncSqliteStorage  # ty: ignore[unresolved-import]
                from hishel.httpx import AsyncCacheClient  # ty: ignore[unresolved-import]
            except ImportError:
                raise ImportError(
                    "hishel is required for caching support. Install it with: pip install discogs-sdk[cache]"
                ) from None
            cache_path = Path(cache_dir) if cache_dir else _default_cache_dir()
            cache_path.mkdir(parents=True, exist_ok=True)
            storage = AsyncSqliteStorage(database_path=cache_path / "cache.db")
            self._http_client = AsyncCacheClient(
                storage=storage,
                headers=self._build_headers(),
                timeout=self.timeout,
            )
            self._owns_client = True
        else:
            self._http_client = httpx.AsyncClient(
                headers=self._build_headers(),
                timeout=self.timeout,
            )
            self._owns_client = True

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

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
