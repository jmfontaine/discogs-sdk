"""Tests for Discogs client constructor branches and lifecycle."""

from __future__ import annotations

import httpx2
import pytest
import respx

from discogs_sdk import Discogs
from discogs_sdk._cache import MemoryCache
from discogs_sdk._exceptions import AuthenticationError
from tests.conftest import BASE_URL, make_identity, make_release


class TestCustomHttpClient:
    def test_injected_client_transmits_sdk_headers(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            custom = httpx2.Client(headers={"X-Trace": "keep-me"})
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
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            custom = httpx2.Client(auth=httpx2.BasicAuth("user", "pass"), headers={"Authorization": "Custom default"})
            client = Discogs(token="secret-token", http_client=custom)
            assert client.releases.get(352665).title
            assert route.calls[0].request.headers["Authorization"] == "Discogs token=secret-token"
            custom.close()

    def test_unauthenticated_client_keeps_custom_auth(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            custom = httpx2.Client(auth=httpx2.BasicAuth("user", "pass"))
            client = Discogs(http_client=custom)
            assert client.releases.get(352665).title
            assert route.calls[0].request.headers["Authorization"].startswith("Basic ")
            custom.close()


class TestCacheIsolation:
    """Cached entries must never cross account or representation boundaries."""

    def test_two_tokens_sharing_a_cache_get_their_own_identity(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/oauth/identity").mock(
                side_effect=[
                    respx.MockResponse(200, json=make_identity(id=1, username="trent_reznor")),
                    respx.MockResponse(200, json=make_identity(id=2, username="atticus_ross")),
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
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/oauth/identity").mock(
                side_effect=[
                    respx.MockResponse(200, json=make_identity()),
                    respx.MockResponse(401, json={"message": "You must authenticate to access this resource."}),
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
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/oauth/identity").respond(200, json=make_identity())
            first = Discogs(token="token-a", cache=True, cache_dir=tmp_path)
            first.user.identity()
            first.close()

            second = Discogs(token="token-a", cache=True, cache_dir=tmp_path)
            assert second.user.identity().username == "trent_reznor"
            assert route.call_count == 1
            second.close()

    def test_media_type_representations_do_not_collide(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").mock(
                side_effect=[
                    respx.MockResponse(200, json=make_release(title="Discogs markup")),
                    respx.MockResponse(200, json=make_release(title="<b>HTML</b>")),
                    respx.MockResponse(200, json=make_release(title="plain text")),
                ]
            )
            cache = MemoryCache(ttl=600)
            clients = {
                "discogs": Discogs(token="t", cache=cache),
                "html": Discogs(token="t", cache=cache, media_type="html"),
                "plaintext": Discogs(token="t", cache=cache, media_type="plaintext"),
            }
            titles = [client.releases.get(352665).title for client in clients.values()]

            assert titles == ["Discogs markup", "<b>HTML</b>", "plain text"]
            assert route.call_count == 3
            for client in clients.values():
                client.close()

    def test_unidentifiable_transport_is_never_cached(self):
        """An injected client's own auth is opaque, so its responses must not be shared."""
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            custom = httpx2.Client(auth=httpx2.BasicAuth("user", "pass"))
            client = Discogs(http_client=custom, cache=True)

            _ = client.releases.get(352665).title
            _ = client.releases.get(352665).title

            assert route.call_count == 2
            client.close()
            custom.close()

    def test_oauth_requests_hit_cache_despite_fresh_signing_values(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
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
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/oauth/identity").respond(200, json=make_identity())
            cache = MemoryCache(ttl=600)
            client = Discogs(token="super-secret-token", cache=cache)
            client.user.identity()
            assert cache._store
            assert all("super-secret-token" not in key for key in cache._store)
            client.close()


class TestCacheBranch:
    def test_caching_disabled_by_default(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            client = Discogs(token="t")
            _ = client.releases.get(352665).title
            _ = client.releases.get(352665).title
            assert route.call_count == 2
            client.close()

    def test_expired_entry_is_refetched(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            client = Discogs(token="t", cache=True, cache_ttl=0)
            _ = client.releases.get(352665).title
            _ = client.releases.get(352665).title
            assert route.call_count == 2  # ttl=0 expires immediately
            client.close()

    def test_sqlite_cache_survives_a_new_client(self, tmp_path):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            first = Discogs(token="t", cache=True, cache_dir=tmp_path)
            _ = first.releases.get(352665).title
            first.close()

            second = Discogs(token="t", cache=True, cache_dir=tmp_path)
            assert second.releases.get(352665).title == "The Downward Spiral"
            assert route.call_count == 1
            second.close()

    def test_custom_cache_instance_receives_the_response(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            cache = MemoryCache(ttl=600)
            client = Discogs(token="t", cache=cache)
            _ = client.releases.get(352665).title
            _ = client.releases.get(352665).title
            assert route.call_count == 1
            assert len(cache._store) == 1
            client.close()

    def test_cached_get_served_without_http(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/1").mock(return_value=respx.MockResponse(200, json={"id": 1}))
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
        content-encoding header, causing httpx2 to double-decompress on cache hit.
        """
        import gzip

        compressed = gzip.compress(b'{"id": 1}')
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/releases/1").mock(
                return_value=respx.MockResponse(
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
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/1").mock(return_value=respx.MockResponse(200, json={"id": 1}))
            client = Discogs(token="t", cache=True)
            client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 1
            with client.no_cache():
                client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 2
            client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 2
            client.close()

    def test_nested_no_cache_scopes_stay_bypassed(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/1").mock(return_value=respx.MockResponse(200, json={"id": 1}))
            client = Discogs(token="t", cache=True)
            client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 1

            with client.no_cache():
                with client.no_cache():
                    client._send("GET", f"{BASE_URL}/releases/1")
                assert route.call_count == 2
                # Still inside the outer scope: must not fall back to the cache.
                client._send("GET", f"{BASE_URL}/releases/1")
                assert route.call_count == 3

            client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 3
            client.close()

    def test_exception_restores_previous_bypass_state(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/1").mock(return_value=respx.MockResponse(200, json={"id": 1}))
            client = Discogs(token="t", cache=True)
            client._send("GET", f"{BASE_URL}/releases/1")

            with client.no_cache():
                with pytest.raises(RuntimeError), client.no_cache():
                    raise RuntimeError("boom")
                client._send("GET", f"{BASE_URL}/releases/1")
                assert route.call_count == 2

            client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 2
            client.close()

    def test_threads_keep_independent_bypass_state(self):
        import threading

        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/1").mock(return_value=respx.MockResponse(200, json={"id": 1}))
            client = Discogs(token="t", cache=True)
            client._send("GET", f"{BASE_URL}/releases/1")
            assert route.call_count == 1

            left_entered = threading.Event()
            right_exited = threading.Event()

            def bypassing():
                with client.no_cache():
                    left_entered.set()
                    right_exited.wait(timeout=5)
                    client._send("GET", f"{BASE_URL}/releases/1")

            def caching():
                left_entered.wait(timeout=5)
                with client.no_cache():
                    client._send("GET", f"{BASE_URL}/releases/1")
                right_exited.set()
                client._send("GET", f"{BASE_URL}/releases/1")

            threads = [threading.Thread(target=bypassing), threading.Thread(target=caching)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)

            # Two bypassed fetches; the sibling's cached read after its own scope
            # exited must not have been forced onto the network.
            assert route.call_count == 3
            client.close()

    def test_clear_cache_forces_a_refetch(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            client = Discogs(token="t", cache=True)
            _ = client.releases.get(352665).title
            client.clear_cache()
            _ = client.releases.get(352665).title
            assert route.call_count == 2
            client.close()

    def test_clear_cache_without_cache(self):
        client = Discogs(token="t", cache=False)
        client.clear_cache()  # should not raise


class TestOAuthInSend:
    def test_oauth_headers_injected(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/releases/1").mock(return_value=respx.MockResponse(200, json={"id": 1}))
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
        custom = httpx2.Client()
        client = Discogs(token="t", http_client=custom)
        client.close()
        assert not custom.is_closed
        custom.close()

    def test_context_manager(self):
        with Discogs(token="t") as client:
            assert isinstance(client, Discogs)


class TestCredentialPrecedence:
    """Precedence is proven by what reaches the wire and whose identity comes back."""

    def test_explicit_token_beats_environment_oauth(self, monkeypatch):
        monkeypatch.setenv("DISCOGS_CONSUMER_KEY", "env-key")
        monkeypatch.setenv("DISCOGS_CONSUMER_SECRET", "env-secret")
        monkeypatch.setenv("DISCOGS_ACCESS_TOKEN", "env-at")
        monkeypatch.setenv("DISCOGS_ACCESS_TOKEN_SECRET", "env-ats")

        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/oauth/identity").respond(200, json=make_identity(username="trent_reznor"))
            client = Discogs(token="explicit-token")

            assert client.user.identity().username == "trent_reznor"

            assert route.calls[0].request.headers["Authorization"] == "Discogs token=explicit-token"
            client.close()

    def test_explicit_oauth_beats_environment_token(self, monkeypatch):
        monkeypatch.setenv("DISCOGS_TOKEN", "env-token")

        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/oauth/identity").respond(200, json=make_identity(username="atticus_ross"))
            client = Discogs(
                consumer_key="ck",
                consumer_secret="cs",
                access_token="at",
                access_token_secret="ats",
            )

            assert client.user.identity().username == "atticus_ross"

            authorization = route.calls[0].request.headers["Authorization"]
            assert authorization.startswith("OAuth ")
            assert 'oauth_token="at"' in authorization
            assert "env-token" not in authorization
            client.close()

    def test_explicit_consumer_does_not_borrow_environment_oauth(self, monkeypatch):
        monkeypatch.setenv("DISCOGS_ACCESS_TOKEN", "env-at")
        monkeypatch.setenv("DISCOGS_ACCESS_TOKEN_SECRET", "env-ats")

        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            client = Discogs(consumer_key="ck", consumer_secret="cs")

            _ = client.releases.get(352665).title

            assert route.calls[0].request.headers["Authorization"] == "Discogs key=ck, secret=cs"
            client.close()
