"""Tests for Discogs client constructor branches and lifecycle."""

from __future__ import annotations

import httpx
import respx

from discogs_sdk import Discogs
from discogs_sdk._cache import MemoryCache, SQLiteCache
from tests.conftest import BASE_URL


class TestCustomHttpClient:
    def test_custom_client_injection(self):
        custom = httpx.Client()
        client = Discogs(token="t", http_client=custom)
        assert client._http_client is custom
        assert client._owns_client is False
        custom.close()


class TestCacheBranch:
    def test_cache_true_creates_memory_cache(self):
        client = Discogs(token="t", cache=True)
        assert isinstance(client._cache, MemoryCache)

    def test_cache_false_leaves_cache_none(self):
        client = Discogs(token="t", cache=False)
        assert client._cache is None

    def test_cache_ttl_passed_through(self):
        client = Discogs(token="t", cache=True, cache_ttl=120)
        assert client._cache is not None
        assert client._cache._ttl == 120

    def test_cache_dir_creates_sqlite_cache(self, tmp_path):
        client = Discogs(token="t", cache=True, cache_dir=tmp_path)
        assert isinstance(client._cache, SQLiteCache)
        client._cache.close()

    def test_cached_get_served_without_http(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/1").mock(return_value=httpx.Response(200, json={"id": 1}))
            client = Discogs(token="t", cache=True)
            r1 = client._send("GET", f"{BASE_URL}/releases/1")
            assert r1.status_code == 200
            assert route.call_count == 1
            r2 = client._send("GET", f"{BASE_URL}/releases/1")
            assert r2.status_code == 200
            assert route.call_count == 1
            client.close()

    def test_no_cache_context_manager(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/1").mock(return_value=httpx.Response(200, json={"id": 1}))
            client = Discogs(token="t", cache=True)
            client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 1
            with client.no_cache():
                client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 2
            client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 2
            client.close()

    def test_clear_cache_noop_when_disabled(self):
        client = Discogs(token="t", cache=False)
        client.clear_cache()  # should not raise


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
