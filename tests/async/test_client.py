"""Tests for AsyncDiscogs client constructor branches and lifecycle."""

from __future__ import annotations

import httpx
import pytest
import respx

from discogs_sdk import AsyncDiscogs
from discogs_sdk._cache import MemoryCache
from discogs_sdk._exceptions import AuthenticationError, NotFoundError
from tests.conftest import BASE_URL, make_identity, make_release


class TestCustomHttpClient:
    async def test_injected_client_transmits_sdk_headers(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            custom = httpx.AsyncClient(headers={"X-Trace": "keep-me"})
            client = AsyncDiscogs(token="secret-token", http_client=custom, media_type="html")
            await client.releases.get(352665)
            request = route.calls[0].request
            assert request.headers["Authorization"] == "Discogs token=secret-token"
            assert request.headers["Accept"] == "application/vnd.discogs.v2.html+json"
            assert request.headers["User-Agent"].startswith("discogs-sdk/")
            assert request.headers["X-Trace"] == "keep-me"
            await client.close()
            assert custom.is_closed is False
            assert custom.headers["X-Trace"] == "keep-me"
            await custom.aclose()

    async def test_custom_client_auth_cannot_replace_sdk_credentials(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            custom = httpx.AsyncClient(
                auth=httpx.BasicAuth("user", "pass"), headers={"Authorization": "Custom default"}
            )
            client = AsyncDiscogs(token="secret-token", http_client=custom)
            await client.releases.get(352665)
            assert route.calls[0].request.headers["Authorization"] == "Discogs token=secret-token"
            await custom.aclose()

    async def test_unauthenticated_client_keeps_custom_auth(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            custom = httpx.AsyncClient(auth=httpx.BasicAuth("user", "pass"))
            client = AsyncDiscogs(http_client=custom)
            await client.releases.get(352665)
            assert route.calls[0].request.headers["Authorization"].startswith("Basic ")
            await custom.aclose()


class TestCacheIsolation:
    """Cached entries must never cross account or representation boundaries."""

    async def test_two_tokens_sharing_a_cache_get_their_own_identity(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/oauth/identity").mock(
                side_effect=[
                    httpx.Response(200, json=make_identity(id=1, username="trent_reznor")),
                    httpx.Response(200, json=make_identity(id=2, username="atticus_ross")),
                ]
            )
            cache = MemoryCache(ttl=600)
            client_a = AsyncDiscogs(token="token-a", cache=cache)
            client_b = AsyncDiscogs(token="token-b", cache=cache)
            assert (await client_a.user.identity()).username == "trent_reznor"
            assert (await client_b.user.identity()).username == "atticus_ross"
            assert route.call_count == 2
            await client_a.close()
            await client_b.close()

    async def test_unauthenticated_client_cannot_read_an_authenticated_entry(self, tmp_path):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/oauth/identity").mock(
                side_effect=[
                    httpx.Response(200, json=make_identity()),
                    httpx.Response(401, json={"message": "You must authenticate to access this resource."}),
                ]
            )
            authenticated = AsyncDiscogs(token="token-a", cache=True, cache_dir=tmp_path)
            assert (await authenticated.user.identity()).username == "trent_reznor"
            await authenticated.close()

            anonymous = AsyncDiscogs(cache=True, cache_dir=tmp_path)
            with pytest.raises(AuthenticationError):
                await anonymous.user.identity()
            assert route.call_count == 2
            await anonymous.close()

    async def test_same_credentials_reuse_entry_after_reopening_sqlite(self, tmp_path):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/oauth/identity").respond(200, json=make_identity())
            first = AsyncDiscogs(token="token-a", cache=True, cache_dir=tmp_path)
            await first.user.identity()
            await first.close()

            second = AsyncDiscogs(token="token-a", cache=True, cache_dir=tmp_path)
            assert (await second.user.identity()).username == "trent_reznor"
            assert route.call_count == 1
            await second.close()

    async def test_media_type_representations_do_not_collide(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").mock(
                side_effect=[
                    httpx.Response(200, json=make_release(title="Discogs markup")),
                    httpx.Response(200, json=make_release(title="<b>HTML</b>")),
                    httpx.Response(200, json=make_release(title="plain text")),
                ]
            )
            cache = MemoryCache(ttl=600)
            clients = {
                "discogs": AsyncDiscogs(token="t", cache=cache),
                "html": AsyncDiscogs(token="t", cache=cache, media_type="html"),
                "plaintext": AsyncDiscogs(token="t", cache=cache, media_type="plaintext"),
            }
            titles = [(await client.releases.get(352665)).title for client in clients.values()]

            assert titles == ["Discogs markup", "<b>HTML</b>", "plain text"]
            assert route.call_count == 3
            for client in clients.values():
                await client.close()

    async def test_unidentifiable_transport_is_never_cached(self):
        """An injected client's own auth is opaque, so its responses must not be shared."""
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            custom = httpx.AsyncClient(auth=httpx.BasicAuth("user", "pass"))
            client = AsyncDiscogs(http_client=custom, cache=True)

            await client.releases.get(352665)
            await client.releases.get(352665)

            assert route.call_count == 2
            await client.close()
            await custom.aclose()

    async def test_oauth_requests_hit_cache_despite_fresh_signing_values(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/oauth/identity").respond(200, json=make_identity())
            client = AsyncDiscogs(
                consumer_key="ck",
                consumer_secret="cs",
                access_token="at",
                access_token_secret="ats",
                cache=True,
            )
            await client.user.identity()
            await client.user.identity()
            assert route.call_count == 1
            # Signing material is fresh per request, yet the key stayed stable.
            assert client._build_oauth_header_for_request() != client._build_oauth_header_for_request()
            await client.close()

    async def test_cache_keys_never_contain_credentials(self):
        with respx.mock(base_url=BASE_URL) as router:
            router.get("/oauth/identity").respond(200, json=make_identity())
            cache = MemoryCache(ttl=600)
            client = AsyncDiscogs(token="super-secret-token", cache=cache)
            await client.user.identity()
            assert cache._store
            assert all("super-secret-token" not in key for key in cache._store)
            await client.close()


class TestCacheBranch:
    async def test_caching_disabled_by_default(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            client = AsyncDiscogs(token="t")
            await client.releases.get(352665)
            await client.releases.get(352665)
            assert route.call_count == 2
            await client.close()

    async def test_expired_entry_is_refetched(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            client = AsyncDiscogs(token="t", cache=True, cache_ttl=0)
            await client.releases.get(352665)
            await client.releases.get(352665)
            assert route.call_count == 2  # ttl=0 expires immediately
            await client.close()

    async def test_sqlite_cache_survives_a_new_client(self, tmp_path):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            first = AsyncDiscogs(token="t", cache=True, cache_dir=tmp_path)
            await first.releases.get(352665)
            await first.close()

            second = AsyncDiscogs(token="t", cache=True, cache_dir=tmp_path)
            assert (await second.releases.get(352665)).title == "The Downward Spiral"
            assert route.call_count == 1
            await second.close()

    async def test_custom_cache_instance_receives_the_response(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            cache = MemoryCache(ttl=600)
            client = AsyncDiscogs(token="t", cache=cache)
            await client.releases.get(352665)
            await client.releases.get(352665)
            assert route.call_count == 1
            assert len(cache._store) == 1
            await client.close()

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
            for _ in range(2):
                with pytest.raises(NotFoundError):
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

    async def test_nested_no_cache_scopes_stay_bypassed(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/1").mock(return_value=httpx.Response(200, json={"id": 1}))
            client = AsyncDiscogs(token="t", cache=True)
            await client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 1

            async with client.no_cache():
                async with client.no_cache():
                    await client._send("GET", f"{BASE_URL}/releases/1")
                assert route.call_count == 2
                # Still inside the outer scope: must not fall back to the cache.
                await client._send("GET", f"{BASE_URL}/releases/1")
                assert route.call_count == 3

            await client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 3
            await client.close()

    async def test_exception_restores_previous_bypass_state(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/1").mock(return_value=httpx.Response(200, json={"id": 1}))
            client = AsyncDiscogs(token="t", cache=True)
            await client._send("GET", f"{BASE_URL}/releases/1")

            async with client.no_cache():
                with pytest.raises(RuntimeError):
                    async with client.no_cache():
                        raise RuntimeError("boom")
                await client._send("GET", f"{BASE_URL}/releases/1")
                assert route.call_count == 2

            await client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 2
            await client.close()

    async def test_concurrent_tasks_keep_independent_bypass_state(self):
        import asyncio

        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/1").mock(return_value=httpx.Response(200, json={"id": 1}))
            client = AsyncDiscogs(token="t", cache=True)
            await client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 1

            left_entered = asyncio.Event()
            right_exited = asyncio.Event()

            async def bypassing():
                async with client.no_cache():
                    left_entered.set()
                    await right_exited.wait()
                    await client._send("GET", f"{BASE_URL}/releases/1")

            async def caching():
                await left_entered.wait()
                async with client.no_cache():
                    await client._send("GET", f"{BASE_URL}/releases/1")
                right_exited.set()
                await client._send("GET", f"{BASE_URL}/releases/1")

            await asyncio.gather(bypassing(), caching())

            # Two bypassed fetches; the sibling's cached read after its own scope
            # exited must not have been forced onto the network.
            assert route.call_count == 3
            await client.close()

    async def test_clear_cache_forces_a_refetch(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            client = AsyncDiscogs(token="t", cache=True)
            await client.releases.get(352665)
            client.clear_cache()
            await client.releases.get(352665)
            assert route.call_count == 2
            await client.close()

    def test_clear_cache_without_cache(self):
        client = AsyncDiscogs(token="t", cache=False)
        client.clear_cache()  # should not raise


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


class TestCredentialPrecedence:
    """Precedence is proven by what reaches the wire and whose identity comes back."""

    async def test_explicit_token_beats_environment_oauth(self, monkeypatch):
        monkeypatch.setenv("DISCOGS_CONSUMER_KEY", "env-key")
        monkeypatch.setenv("DISCOGS_CONSUMER_SECRET", "env-secret")
        monkeypatch.setenv("DISCOGS_ACCESS_TOKEN", "env-at")
        monkeypatch.setenv("DISCOGS_ACCESS_TOKEN_SECRET", "env-ats")

        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/oauth/identity").respond(200, json=make_identity(username="trent_reznor"))
            client = AsyncDiscogs(token="explicit-token")

            assert (await client.user.identity()).username == "trent_reznor"

            assert route.calls[0].request.headers["Authorization"] == "Discogs token=explicit-token"
            await client.close()

    async def test_explicit_oauth_beats_environment_token(self, monkeypatch):
        monkeypatch.setenv("DISCOGS_TOKEN", "env-token")

        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/oauth/identity").respond(200, json=make_identity(username="atticus_ross"))
            client = AsyncDiscogs(
                consumer_key="ck",
                consumer_secret="cs",
                access_token="at",
                access_token_secret="ats",
            )

            assert (await client.user.identity()).username == "atticus_ross"

            authorization = route.calls[0].request.headers["Authorization"]
            assert authorization.startswith("OAuth ")
            assert 'oauth_token="at"' in authorization
            assert "env-token" not in authorization
            await client.close()

    async def test_explicit_consumer_does_not_borrow_environment_oauth(self, monkeypatch):
        monkeypatch.setenv("DISCOGS_ACCESS_TOKEN", "env-at")
        monkeypatch.setenv("DISCOGS_ACCESS_TOKEN_SECRET", "env-ats")

        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            client = AsyncDiscogs(consumer_key="ck", consumer_secret="cs")

            await client.releases.get(352665)

            assert route.calls[0].request.headers["Authorization"] == "Discogs key=ck, secret=cs"
            await client.close()
