"""Tests for Discogs client constructor branches and lifecycle."""

from __future__ import annotations

import httpx
import pytest
import respx

from discogs_sdk import Discogs
from discogs_sdk._cache import MemoryCache, SQLiteCache
from discogs_sdk._exceptions import AuthenticationError
from tests.conftest import BASE_URL, make_identity, make_release


class TestCustomHttpClient:
    def test_custom_client_injection(self):
        custom = httpx.Client()
        client = Discogs(token="t", http_client=custom)
        assert client._http_client is custom
        assert client._owns_client is False
        custom.close()

    def test_injected_client_transmits_sdk_headers(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            custom = httpx.Client(headers={"X-Trace": "keep-me"})
            client = Discogs(token="secret-token", http_client=custom, media_type="html")
            assert client.releases.get(352665).title
            request = route.calls[0].request
            assert request.headers["Authorization"] == "Discogs token=secret-token"
            assert request.headers["Accept"] == "application/vnd.discogs.v2.html+json"
            assert request.headers["User-Agent"].startswith("discogs-sdk/")
            assert request.headers["X-Trace"] == "keep-me"
            client.close()
            assert custom.is_closed is False
            assert custom.headers["X-Trace"] == "keep-me"
            custom.close()

    def test_custom_client_auth_cannot_replace_sdk_credentials(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            custom = httpx.Client(auth=httpx.BasicAuth("user", "pass"), headers={"Authorization": "Custom default"})
            client = Discogs(token="secret-token", http_client=custom)
            assert client.releases.get(352665).title
            assert route.calls[0].request.headers["Authorization"] == "Discogs token=secret-token"
            custom.close()

    def test_unauthenticated_client_keeps_custom_auth(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            custom = httpx.Client(auth=httpx.BasicAuth("user", "pass"))
            client = Discogs(http_client=custom)
            assert client.releases.get(352665).title
            assert route.calls[0].request.headers["Authorization"].startswith("Basic ")
            custom.close()


class TestCacheIsolation:
    """Cached entries must never cross account or representation boundaries."""

    def test_two_tokens_sharing_a_cache_get_their_own_identity(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/oauth/identity").mock(
                side_effect=[
                    httpx.Response(200, json=make_identity(id=1, username="trent_reznor")),
                    httpx.Response(200, json=make_identity(id=2, username="atticus_ross")),
                ]
            )
            cache = MemoryCache(ttl=600)
            client_a = Discogs(token="token-a", cache=cache)
            client_b = Discogs(token="token-b", cache=cache)
            assert client_a.user.identity().username == "trent_reznor"
            assert client_b.user.identity().username == "atticus_ross"
            assert route.call_count == 2
            client_a.close()
            client_b.close()

    def test_unauthenticated_client_cannot_read_an_authenticated_entry(self, tmp_path):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/oauth/identity").mock(
                side_effect=[
                    httpx.Response(200, json=make_identity()),
                    httpx.Response(401, json={"message": "You must authenticate to access this resource."}),
                ]
            )
            authenticated = Discogs(token="token-a", cache=True, cache_dir=tmp_path)
            assert authenticated.user.identity().username == "trent_reznor"
            authenticated.close()

            anonymous = Discogs(cache=True, cache_dir=tmp_path)
            with pytest.raises(AuthenticationError):
                anonymous.user.identity()
            assert route.call_count == 2
            anonymous.close()

    def test_same_credentials_reuse_entry_after_reopening_sqlite(self, tmp_path):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/oauth/identity").respond(200, json=make_identity())
            first = Discogs(token="token-a", cache=True, cache_dir=tmp_path)
            first.user.identity()
            first.close()

            second = Discogs(token="token-a", cache=True, cache_dir=tmp_path)
            assert second.user.identity().username == "trent_reznor"
            assert route.call_count == 1
            second.close()

    def test_media_type_representations_do_not_collide(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/releases/352665").mock(
                side_effect=[
                    httpx.Response(200, json=make_release(title="Discogs markup")),
                    httpx.Response(200, json=make_release(title="<b>HTML</b>")),
                ]
            )
            cache = MemoryCache(ttl=600)
            discogs_markup = Discogs(token="t", cache=cache)
            html = Discogs(token="t", cache=cache, media_type="html")
            assert discogs_markup.releases.get(352665).title == "Discogs markup"
            assert html.releases.get(352665).title == "<b>HTML</b>"
            assert route.call_count == 2
            discogs_markup.close()
            html.close()

    def test_oauth_requests_hit_cache_despite_fresh_signing_values(self):
        with respx.mock(base_url=BASE_URL) as router:
            route = router.get("/oauth/identity").respond(200, json=make_identity())
            client = Discogs(
                consumer_key="ck",
                consumer_secret="cs",
                access_token="at",
                access_token_secret="ats",
                cache=True,
            )
            client.user.identity()
            client.user.identity()
            assert route.call_count == 1
            # Signing material is fresh per request, yet the key stayed stable.
            assert client._build_oauth_header_for_request() != client._build_oauth_header_for_request()
            client.close()

    def test_cache_keys_never_contain_credentials(self):
        with respx.mock(base_url=BASE_URL) as router:
            router.get("/oauth/identity").respond(200, json=make_identity())
            cache = MemoryCache(ttl=600)
            client = Discogs(token="super-secret-token", cache=cache)
            client.user.identity()
            assert cache._store
            assert all("super-secret-token" not in key for key in cache._store)
            client.close()


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

    def test_cache_accepts_response_cache_instance(self):
        cache = MemoryCache(ttl=60)
        client = Discogs(token="t", cache=cache)
        assert client._cache is cache

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

    def test_cached_response_strips_content_encoding(self):
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
            client = Discogs(token="t", cache=True)
            r1 = client._send("GET", f"{BASE_URL}/releases/1")
            assert r1.json() == {"id": 1}
            # Cache hit: must not fail with zlib/decompression error
            r2 = client._send("GET", f"{BASE_URL}/releases/1")
            assert r2.json() == {"id": 1}
            assert "content-encoding" not in r2.headers
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

    def test_clear_cache_with_cache(self):
        client = Discogs(token="t", cache=True)
        assert client._cache is not None
        client._cache.set("k", 200, {}, b"x")
        client.clear_cache()
        assert client._cache.get("k") is None

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
