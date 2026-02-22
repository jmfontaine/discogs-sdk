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

    def test_cache_with_hishel(self, tmp_path):
        mock_cache_client = MagicMock()
        mock_storage = MagicMock()
        mock_hishel = MagicMock()
        mock_hishel.AsyncSqliteStorage = MagicMock(return_value=mock_storage)
        mock_httpx_module = MagicMock()
        mock_httpx_module.AsyncCacheClient = MagicMock(return_value=mock_cache_client)
        with patch.dict(sys.modules, {"hishel": mock_hishel, "hishel.httpx": mock_httpx_module}):
            client = AsyncDiscogs(token="t", cache=True, cache_dir=tmp_path)
            assert client._http_client is mock_cache_client
            assert client._owns_client is True

    def test_cache_default_dir(self, tmp_path):
        mock_cache_client = MagicMock()
        mock_storage = MagicMock()
        mock_hishel = MagicMock()
        mock_hishel.AsyncSqliteStorage = MagicMock(return_value=mock_storage)
        mock_httpx_module = MagicMock()
        mock_httpx_module.AsyncCacheClient = MagicMock(return_value=mock_cache_client)
        xdg_cache = tmp_path / "xdg-cache"
        with (
            patch.dict(sys.modules, {"hishel": mock_hishel, "hishel.httpx": mock_httpx_module}),
            patch.dict("os.environ", {"XDG_CACHE_HOME": str(xdg_cache)}),
        ):
            AsyncDiscogs(token="t", cache=True)
            db_path = mock_hishel.AsyncSqliteStorage.call_args[1]["database_path"]
            assert db_path == xdg_cache / "discogs-sdk" / "cache.db"
            assert (xdg_cache / "discogs-sdk").is_dir()

    def test_cache_custom_dir(self, tmp_path):
        mock_cache_client = MagicMock()
        mock_storage = MagicMock()
        mock_hishel = MagicMock()
        mock_hishel.AsyncSqliteStorage = MagicMock(return_value=mock_storage)
        mock_httpx_module = MagicMock()
        mock_httpx_module.AsyncCacheClient = MagicMock(return_value=mock_cache_client)
        custom_dir = tmp_path / "my-cache"
        with patch.dict(sys.modules, {"hishel": mock_hishel, "hishel.httpx": mock_httpx_module}):
            AsyncDiscogs(token="t", cache=True, cache_dir=custom_dir)
            db_path = mock_hishel.AsyncSqliteStorage.call_args[1]["database_path"]
            assert db_path == custom_dir / "cache.db"
            assert custom_dir.is_dir()

    def test_cache_storage_passed_to_client(self, tmp_path):
        mock_cache_client = MagicMock()
        mock_storage = MagicMock()
        mock_hishel = MagicMock()
        mock_hishel.AsyncSqliteStorage = MagicMock(return_value=mock_storage)
        mock_httpx_module = MagicMock()
        mock_httpx_module.AsyncCacheClient = MagicMock(return_value=mock_cache_client)
        with patch.dict(sys.modules, {"hishel": mock_hishel, "hishel.httpx": mock_httpx_module}):
            AsyncDiscogs(token="t", cache=True, cache_dir=tmp_path)
            mock_httpx_module.AsyncCacheClient.assert_called_once()
            call_kwargs = mock_httpx_module.AsyncCacheClient.call_args[1]
            assert call_kwargs["storage"] is mock_storage


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
