"""Tests for Discogs client constructor branches and lifecycle."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from discogs_sdk import Discogs
from tests.conftest import BASE_URL


class TestCustomHttpClient:
    def test_custom_client_injection(self):
        custom = httpx.Client()
        client = Discogs(token="t", http_client=custom)
        assert client._http_client is custom
        assert client._owns_client is False
        custom.close()


class TestCacheBranch:
    def test_cache_without_hishel_raises(self):
        with patch.dict(sys.modules, {"hishel": None, "hishel.httpx": None}):
            with pytest.raises(ImportError, match="hishel is required"):
                Discogs(token="t", cache=True)

    def test_cache_with_hishel(self):
        mock_cache_client = MagicMock()
        mock_module = MagicMock()
        mock_module.SyncCacheClient = MagicMock(return_value=mock_cache_client)
        with patch.dict(sys.modules, {"hishel": MagicMock(), "hishel.httpx": mock_module}):
            client = Discogs(token="t", cache=True)
            assert client._http_client is mock_cache_client
            assert client._owns_client is True


class TestOAuthInSend:
    def test_oauth_headers_injected(self):
        with respx.mock(base_url=BASE_URL) as router:
            router.get("/releases/1").mock(return_value=httpx.Response(200, json={"id": 1}))
            client = Discogs(
                consumer_key="ck",
                consumer_secret="cs",
                access_token="at",
                access_token_secret="ats",
            )
            client._send("GET", f"{BASE_URL}/releases/1")
            request = router.calls[0].request
            assert "OAuth" in request.headers["Authorization"]
            client.close()


class TestLifecycle:
    def test_close_when_owns_client(self):
        client = Discogs(token="t")
        assert client._owns_client is True
        client.close()

    def test_close_when_not_owns_client(self):
        custom = httpx.Client()
        client = Discogs(token="t", http_client=custom)
        client.close()
        assert not custom.is_closed
        custom.close()

    def test_context_manager(self):
        with Discogs(token="t") as client:
            assert isinstance(client, Discogs)
