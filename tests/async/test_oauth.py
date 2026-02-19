"""Tests for async OAuth helpers."""

from __future__ import annotations

import httpx
import respx

from discogs_sdk._async._oauth import AccessToken, RequestToken, get_access_token, get_request_token


BASE_URL = "https://api.discogs.com"


class TestGetRequestToken:
    async def test_returns_request_token(self):
        with respx.mock(base_url=BASE_URL) as router:
            router.get("/oauth/request_token").mock(
                return_value=httpx.Response(200, text="oauth_token=req-token&oauth_token_secret=req-secret")
            )
            result = await get_request_token("ck", "cs")
            assert isinstance(result, RequestToken)
            assert result.oauth_token == "req-token"
            assert result.oauth_token_secret == "req-secret"
            assert "oauth_token=req-token" in result.authorize_url

    async def test_custom_callback_url(self):
        with respx.mock(base_url=BASE_URL) as router:
            router.get("/oauth/request_token").mock(
                return_value=httpx.Response(200, text="oauth_token=t&oauth_token_secret=s")
            )
            result = await get_request_token("ck", "cs", callback_url="https://example.com/cb")
            assert result.oauth_token == "t"


class TestGetAccessToken:
    async def test_returns_access_token(self):
        with respx.mock(base_url=BASE_URL) as router:
            router.post("/oauth/access_token").mock(
                return_value=httpx.Response(200, text="oauth_token=access-token&oauth_token_secret=access-secret")
            )
            result = await get_access_token("ck", "cs", "req-token", "req-secret", "verifier-123")
            assert isinstance(result, AccessToken)
            assert result.oauth_token == "access-token"
            assert result.oauth_token_secret == "access-secret"
