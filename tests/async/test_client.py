"""Tests for AsyncDiscogs client constructor branches and lifecycle."""

from __future__ import annotations

import httpx
import respx

from discogs_sdk import AsyncDiscogs
from discogs_sdk._cache import MemoryCache, SQLiteCache
from tests.conftest import BASE_URL


class TestCustomHttpClient:
    async def test_custom_client_injection(self):
        custom = httpx.AsyncClient()
        client = AsyncDiscogs(token="t", http_client=custom)
        assert client._http_client is custom
        assert client._owns_client is False
        await custom.aclose()


class TestCacheBranch:
    def test_cache_true_creates_memory_cache(self):
        client = AsyncDiscogs(token="t", cache=True)
        assert isinstance(client._cache, MemoryCache)

    def test_cache_false_leaves_cache_none(self):
        client = AsyncDiscogs(token="t", cache=False)
        assert client._cache is None

    def test_cache_ttl_passed_through(self):
        client = AsyncDiscogs(token="t", cache=True, cache_ttl=120)
        assert client._cache is not None
        assert client._cache._ttl == 120

    def test_cache_dir_creates_sqlite_cache(self, tmp_path):
        client = AsyncDiscogs(token="t", cache=True, cache_dir=tmp_path)
        assert isinstance(client._cache, SQLiteCache)
        client._cache.close()

    def test_cache_accepts_response_cache_instance(self):
        cache = MemoryCache(ttl=60)
        client = AsyncDiscogs(token="t", cache=cache)
        assert client._cache is cache

    async def test_cached_get_served_without_http(self):
        """Second GET for the same URL returns cached response, no network call."""
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/1").mock(return_value=httpx.Response(200, json={"id": 1}))
            client = AsyncDiscogs(token="t", cache=True)
            # First call: hits the network
            r1 = await client._send("GET", f"{BASE_URL}/releases/1")
            assert r1.status_code == 200
            assert route.call_count == 1
            # Second call: served from cache
            r2 = await client._send("GET", f"{BASE_URL}/releases/1")
            assert r2.status_code == 200
            assert route.call_count == 1  # no additional HTTP call
            await client.close()

    async def test_cached_response_strips_content_encoding(self):
        """Cache hit with original content-encoding: gzip must not corrupt the body.

        Regression: the cache stored decompressed bodies with the original
        content-encoding header, causing httpx to double-decompress on cache hit.
        """
        import gzip

        compressed = gzip.compress(b'{"id": 1}')
        with respx.mock(base_url=BASE_URL) as router:
            router.get("/releases/1").mock(
                return_value=httpx.Response(
                    200,
                    content=compressed,
                    headers={"content-encoding": "gzip", "content-type": "application/json"},
                )
            )
            client = AsyncDiscogs(token="t", cache=True)
            r1 = await client._send("GET", f"{BASE_URL}/releases/1")
            assert r1.json() == {"id": 1}
            # Cache hit: must not fail with zlib/decompression error
            r2 = await client._send("GET", f"{BASE_URL}/releases/1")
            assert r2.json() == {"id": 1}
            assert "content-encoding" not in r2.headers
            await client.close()

    async def test_post_not_cached(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.post("/some/endpoint").mock(return_value=httpx.Response(200, json={}))
            client = AsyncDiscogs(token="t", cache=True)
            await client._send("POST", f"{BASE_URL}/some/endpoint")
            await client._send("POST", f"{BASE_URL}/some/endpoint")
            assert route.call_count == 2
            await client.close()

    async def test_non_2xx_not_cached(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/404").mock(return_value=httpx.Response(404, json={"message": "not found"}))
            client = AsyncDiscogs(token="t", cache=True, max_retries=0)
            await client._send("GET", f"{BASE_URL}/releases/404")
            await client._send("GET", f"{BASE_URL}/releases/404")
            assert route.call_count == 2
            await client.close()

    async def test_no_cache_context_manager(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/1").mock(return_value=httpx.Response(200, json={"id": 1}))
            client = AsyncDiscogs(token="t", cache=True)
            # Populate cache
            await client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 1
            # Inside no_cache: bypasses cache
            async with client.no_cache():
                await client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 2
            # Outside no_cache: cache is re-enabled
            await client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 2  # served from cache
            await client.close()

    def test_clear_cache_with_cache(self):
        client = AsyncDiscogs(token="t", cache=True)
        assert client._cache is not None
        client._cache.set("k", 200, {}, b"x")
        client.clear_cache()
        assert client._cache.get("k") is None

    def test_clear_cache_without_cache(self):
        client = AsyncDiscogs(token="t", cache=False)
        client.clear_cache()  # should not raise

    async def test_close_closes_sqlite_cache(self, tmp_path):
        client = AsyncDiscogs(token="t", cache=True, cache_dir=tmp_path)
        assert isinstance(client._cache, SQLiteCache)
        await client.close()
        assert client._cache._db is None  # SQLite connection closed


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
