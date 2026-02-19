from __future__ import annotations

import importlib.metadata
import logging
import os
import random
import time
import urllib.parse
from typing import Any

from discogs_sdk._exceptions import (
    AuthenticationError,
    DiscogsAPIError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)

logger = logging.getLogger("discogs_sdk")

DEFAULT_BASE_URL = "https://api.discogs.com"
DEFAULT_TIMEOUT = 30.0
_RETRY_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

try:
    _SDK_VERSION = importlib.metadata.version("discogs-sdk")
except importlib.metadata.PackageNotFoundError:  # pragma: no cover — package is always installed when tests run
    _SDK_VERSION = "0.0.0"

USER_AGENT = f"discogs-sdk/{_SDK_VERSION} +https://github.com/jmfontaine/discogs-sdk"


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
    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": _generate_nonce(),
        "oauth_signature": f"{consumer_secret}&{token_secret}",
        "oauth_signature_method": "PLAINTEXT",
        "oauth_timestamp": str(int(time.time())),
    }
    if token:
        params["oauth_token"] = token
    if verifier:
        params["oauth_verifier"] = verifier
    if callback:
        params["oauth_callback"] = callback
    header_parts = ", ".join(f'{k}="{urllib.parse.quote(v, safe="")}"' for k, v in params.items())
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
    ) -> None:
        self.base_url: str = base_url.rstrip("/")
        self.timeout: float = timeout
        self.max_retries: int = max_retries
        self._user_agent: str = user_agent if user_agent else USER_AGENT

        # Resolve credentials: constructor arg → env var
        self._token = token or os.environ.get("DISCOGS_TOKEN")
        self._consumer_key = consumer_key or os.environ.get("DISCOGS_CONSUMER_KEY")
        self._consumer_secret = consumer_secret or os.environ.get("DISCOGS_CONSUMER_SECRET")
        self._access_token = access_token or os.environ.get("DISCOGS_ACCESS_TOKEN")
        self._access_token_secret = access_token_secret or os.environ.get("DISCOGS_ACCESS_TOKEN_SECRET")

        if self._token:
            logger.debug("Auth: personal access token")
        elif self._uses_oauth:
            logger.debug("Auth: OAuth 1.0a")
        elif self._consumer_key:
            logger.debug("Auth: consumer key/secret")
        else:
            logger.debug("Auth: none (unauthenticated)")

    @property
    def _uses_oauth(self) -> bool:
        return bool(self._consumer_key and self._consumer_secret and self._access_token and self._access_token_secret)

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/json",
        }
        if self._token:
            headers["Authorization"] = f"Discogs token={self._token}"
        elif self._consumer_key and self._consumer_secret and not self._access_token:
            headers["Authorization"] = f"Discogs key={self._consumer_key}, secret={self._consumer_secret}"
        # OAuth headers are per-request (need fresh nonce/timestamp),
        # so they are added in _build_oauth_header_for_request() instead.
        return headers

    def _build_oauth_header_for_request(self) -> str:
        if not (self._consumer_key and self._consumer_secret):
            raise ValueError("OAuth requires consumer_key and consumer_secret")
        if not (self._access_token and self._access_token_secret):
            raise ValueError("OAuth requires access_token and access_token_secret")
        return build_oauth_header(
            consumer_key=self._consumer_key,
            consumer_secret=self._consumer_secret,
            token=self._access_token,
            token_secret=self._access_token_secret,
        )

    def _build_url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _retry_delay(self, attempt: int, retry_after: str | None = None) -> float:
        if retry_after is not None:
            try:
                return float(retry_after)
            except ValueError:
                pass
        # Exponential backoff (2^attempt) capped at 60s, plus random jitter to avoid thundering herd
        return min(2**attempt, 60) + random.random()

    def _maybe_raise(
        self,
        status_code: int,
        body: dict[str, Any] | str,
        *,
        retry_after: str | None = None,
    ) -> None:
        if status_code < 400:
            return

        message = body.get("message", str(body)) if isinstance(body, dict) else body

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
                )
            case _:
                error_cls = DiscogsAPIError

        raise error_cls(
            message,
            status_code=status_code,
            response_body=body,
        )
