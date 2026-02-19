"""Tests for AsyncDiscogs client constructor branches and lifecycle."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from discogs_sdk import AsyncDiscogs
from tests.conftest import BASE_URL


class TestCustomHttpClient:
    async def test_custom_client_injection(self):
        custom = httpx.AsyncClient()
        client = AsyncDiscogs(token="t", http_client=custom)
        assert client._http_client is custom
        assert client._owns_client is False
        await custom.aclose()


class TestCacheBranch:
    def test_cache_without_hishel_raises(self):
        with patch.dict(sys.modules, {"hishel": None, "hishel.httpx": None}):
            with pytest.raises(ImportError, match="hishel is required"):
                AsyncDiscogs(token="t", cache=True)

    def test_cache_with_hishel(self):
        mock_cache_client = MagicMock()
        mock_module = MagicMock()
        mock_module.AsyncCacheClient = MagicMock(return_value=mock_cache_client)
        with patch.dict(sys.modules, {"hishel": MagicMock(), "hishel.httpx": mock_module}):
            client = AsyncDiscogs(token="t", cache=True)
            assert client._http_client is mock_cache_client
            assert client._owns_client is True


class TestOAuthInSend:
    async def test_oauth_headers_injected(self):
        with respx.mock(base_url=BASE_URL) as router:
            router.get("/releases/1").mock(return_value=httpx.Response(200, json={"id": 1}))
            client = AsyncDiscogs(
                consumer_key="ck",
                consumer_secret="cs",
                access_token="at",
                access_token_secret="ats",
            )
            await client._send("GET", f"{BASE_URL}/releases/1")
            request = router.calls[0].request
            assert "OAuth" in request.headers["Authorization"]
            await client.close()


class TestLifecycle:
    async def test_close_when_owns_client(self):
        client = AsyncDiscogs(token="t")
        assert client._owns_client is True
        await client.close()

    async def test_close_when_not_owns_client(self):
        custom = httpx.AsyncClient()
        client = AsyncDiscogs(token="t", http_client=custom)
        # close should not close the custom client
        await client.close()
        # custom client should still be usable (not closed)
        assert not custom.is_closed
        await custom.aclose()

    async def test_context_manager(self):
        async with AsyncDiscogs(token="t") as client:
            assert isinstance(client, AsyncDiscogs)
