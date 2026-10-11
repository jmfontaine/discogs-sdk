"""Tests for Discogs client constructor branches and lifecycle."""

from __future__ import annotations

import json
import logging
import sqlite3
from unittest.mock import patch

import httpx2
import pytest
import respx

import discogs_sdk._sync
from discogs_sdk import Discogs
from discogs_sdk._cache import MemoryCache, SQLiteCache
from discogs_sdk._exceptions import AuthenticationError, DiscogsAPIError
from discogs_sdk._sync._paginator import SyncPage
from tests.conftest import BASE_URL, exclusive_lock, make_identity, make_release


class TestGeneratedSurface:
    @pytest.mark.parametrize(
        "obj", [Discogs, Discogs.__init__, SyncPage], ids=lambda obj: obj.__qualname__
    )
    def test_docstring_describes_sync_usage(self, obj):
        doc = obj.__doc__.lower()
        assert "async" not in doc
        assert "await" not in doc

    def test_package_exports_the_sync_client(self):
        assert discogs_sdk._sync.__all__ == ["Discogs"]


class TestCustomHttpClient:
    def test_injected_client_transmits_sdk_headers(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            custom = httpx2.Client(headers={"X-Trace": "keep-me"})
            client = Discogs(
                token="secret-token", http_client=custom, media_type="html"
            )
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
            custom = httpx2.Client(
                auth=httpx2.BasicAuth("user", "pass"),
                headers={"Authorization": "Custom default"},
            )
            client = Discogs(token="secret-token", http_client=custom)
            assert client.releases.get(352665).title
            assert (
                route.calls[0].request.headers["Authorization"]
                == "Discogs token=secret-token"
            )
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
                    respx.MockResponse(
                        200, json=make_identity(id=1, username="trent_reznor")
                    ),
                    respx.MockResponse(
                        200, json=make_identity(id=2, username="atticus_ross")
                    ),
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
                    respx.MockResponse(
                        401,
                        json={
                            "message": "You must authenticate to access this resource."
                        },
                    ),
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
            assert (
                client._build_oauth_header_for_request()
                != client._build_oauth_header_for_request()
            )
            client.close()

    def test_oauth_cache_hit_builds_no_header(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/oauth/identity").respond(200, json=make_identity())
            client = Discogs(
                consumer_key="ck",
                consumer_secret="cs",
                access_token="at",
                access_token_secret="ats",
                cache=True,
            )
            client.user.identity()
            with patch.object(
                client,
                "_build_oauth_header_for_request",
                wraps=client._build_oauth_header_for_request,
            ) as build:
                client.user.identity()
            build.assert_not_called()
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
            route = router.get("/releases/1").mock(
                return_value=respx.MockResponse(200, json={"id": 1})
            )
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
                    headers={
                        "content-encoding": "gzip",
                        "content-type": "application/json",
                    },
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

    def test_only_allow_listed_headers_are_stored(self, tmp_path):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/releases/352665").respond(
                200,
                json=make_release(),
                headers={
                    "ETag": '"abc"',
                    "Last-Modified": "Sat, 10 Oct 2026 00:00:00 GMT",
                    "Set-Cookie": "session=secret",
                    "X-Discogs-Ratelimit": "60",
                    "X-Discogs-Ratelimit-Remaining": "59",
                },
            )
            client = Discogs(token="t", cache=True, cache_dir=tmp_path)
            client.releases.get(352665).title  # noqa: B018 — triggers resolve
            client.close()
        db = sqlite3.connect(tmp_path / "cache.db")
        (headers,) = db.execute("SELECT headers FROM cache_entries").fetchone()
        db.close()
        assert json.loads(headers) == {
            "content-type": "application/json",
            "etag": '"abc"',
            "last-modified": "Sat, 10 Oct 2026 00:00:00 GMT",
        }

    def test_no_cache_context_manager(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/1").mock(
                return_value=respx.MockResponse(200, json={"id": 1})
            )
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
            route = router.get("/releases/1").mock(
                return_value=respx.MockResponse(200, json={"id": 1})
            )
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
            route = router.get("/releases/1").mock(
                return_value=respx.MockResponse(200, json={"id": 1})
            )
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
            route = router.get("/releases/1").mock(
                return_value=respx.MockResponse(200, json={"id": 1})
            )
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

            threads = [
                threading.Thread(target=bypassing),
                threading.Thread(target=caching),
            ]
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


def _entry_count(cache: MemoryCache | SQLiteCache) -> int:
    if isinstance(cache, MemoryCache):
        return len(cache._store)
    assert cache._db is not None
    return cache._db.execute("SELECT count(*) FROM cache_entries").fetchone()[0]


@pytest.fixture(params=["memory", "sqlite"])
def backend(request, tmp_path):
    cache = (
        MemoryCache(ttl=600)
        if request.param == "memory"
        else SQLiteCache(ttl=600, cache_dir=tmp_path)
    )
    yield cache
    cache.close()


# A gateway error page served with a 200, as some proxies do.
_HTML = b"<html>oops</html>"


class TestNonJsonBodiesAreNotCached:
    """A 2xx GET body that is not JSON would fail to parse on every cache hit."""

    @pytest.mark.parametrize(
        ("body", "content_type"),
        [(_HTML, "text/html"), (b"", "application/json")],
        ids=["html", "empty"],
    )
    def test_bad_body_is_not_stored_and_the_next_read_refetches(
        self, backend, body, content_type
    ):
        events = []
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").mock(
                side_effect=[
                    respx.MockResponse(
                        200, content=body, headers={"Content-Type": content_type}
                    ),
                    respx.MockResponse(200, json=make_release()),
                ]
            )
            client = Discogs(token="t", cache=backend, on_request=events.append)
            with pytest.raises(json.JSONDecodeError):
                client.releases.get(352665).title  # noqa: B018 — triggers resolve
            assert events[0].stored is False
            assert _entry_count(backend) == 0

            assert client.releases.get(352665).title == "The Downward Spiral"
            assert route.call_count == 2
            client.close()

    def test_valid_json_is_stored_and_served_from_the_cache(self, backend):
        events = []
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            client = Discogs(token="t", cache=backend, on_request=events.append)
            client.releases.get(352665).title  # noqa: B018 — triggers resolve
            assert client.releases.get(352665).title == "The Downward Spiral"
            assert route.call_count == 1
            client.close()
        assert [(e.stored, e.attempts) for e in events] == [(True, 1), (False, 0)]

    def test_export_download_is_cached_byte_for_byte(self, backend):
        csv = b"listing_id,artist,title\n1,Nine Inch Nails,The Downward Spiral\n"
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/inventory/export/1/download").respond(
                200, content=csv, headers={"Content-Type": "text/csv"}
            )
            client = Discogs(token="t", cache=backend)
            assert client.exports.download(1) == csv
            assert client.exports.download(1) == csv
            assert route.call_count == 1
            client.close()

    def test_new_client_on_the_same_directory_refetches(self, tmp_path):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").mock(
                side_effect=[
                    respx.MockResponse(
                        200, content=_HTML, headers={"Content-Type": "text/html"}
                    ),
                    respx.MockResponse(200, json=make_release()),
                ]
            )
            first = Discogs(token="t", cache=True, cache_dir=tmp_path)
            with pytest.raises(json.JSONDecodeError):
                first.releases.get(352665).title  # noqa: B018 — triggers resolve
            first.close()

            second = Discogs(token="t", cache=True, cache_dir=tmp_path)
            assert second.releases.get(352665).title == "The Downward Spiral"
            assert route.call_count == 2
            second.close()


class TestFailingSQLiteCache:
    """A broken cache database never turns a successful request into an error."""

    def test_locked_database_still_returns_the_response(
        self, tmp_path, caplog, fast_sqlite_busy_timeout
    ):
        events = []
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/releases/352665").respond(200, json=make_release())
            client = Discogs(
                token="t", cache=True, cache_dir=tmp_path, on_request=events.append
            )
            caplog.set_level(logging.WARNING, logger="discogs_sdk")
            with exclusive_lock(tmp_path):
                assert client.releases.get(352665).title == "The Downward Spiral"
            client.close()
        assert [e.source for e in events] == ["network"]
        assert "database is locked" in caplog.text

    def test_garbage_database_file_degrades_to_misses(self, tmp_path):
        (tmp_path / "cache.db").write_bytes(b"this is not a database" * 64)
        events = []
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            client = Discogs(
                token="t", cache=True, cache_dir=tmp_path, on_request=events.append
            )
            for _ in range(2):
                assert client.releases.get(352665).title == "The Downward Spiral"
            client.close()
        assert route.call_count == 2
        assert [e.source for e in events] == ["network", "network"]


class TestOAuthInSend:
    def test_oauth_headers_injected(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/releases/1").mock(
                return_value=respx.MockResponse(200, json={"id": 1})
            )
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


class RecordingCache(MemoryCache):
    def __init__(self) -> None:
        super().__init__(ttl=600)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _interrupted() -> None:
    raise KeyboardInterrupt


class TestCacheOwnership:
    """The client closes only a cache it built; an injected one stays the caller's."""

    def test_closing_one_client_leaves_a_shared_cache_usable(self, tmp_path):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(200, json=make_release())
            cache = SQLiteCache(ttl=600, cache_dir=tmp_path)
            a = Discogs(token="t", cache=cache)
            b = Discogs(token="t", cache=cache)
            _ = a.releases.get(352665).title
            a.close()

            assert b.releases.get(352665).title == "The Downward Spiral"
            assert route.call_count == 1
            assert cache._db is not None
            b.close()
            cache.close()

    def test_owned_sqlite_cache_is_closed(self, tmp_path):
        client = Discogs(token="t", cache=True, cache_dir=tmp_path)
        cache = client._cache
        assert isinstance(cache, SQLiteCache)
        client.close()
        assert cache._db is None

    def test_injected_cache_is_never_closed(self):
        cache = RecordingCache()
        client = Discogs(token="t", cache=cache)
        client.close()
        assert cache.closed is False

    def test_interrupted_http_close_still_closes_owned_cache(
        self, tmp_path, monkeypatch
    ):
        client = Discogs(token="t", cache=True, cache_dir=tmp_path)
        cache = client._cache
        assert isinstance(cache, SQLiteCache)
        monkeypatch.setattr(client._http_client, "close", _interrupted)
        with pytest.raises(KeyboardInterrupt):
            client.close()
        assert cache._db is None
        monkeypatch.undo()
        client._http_client.close()

    def test_interrupted_http_close_leaves_injected_cache_open(self, monkeypatch):
        cache = RecordingCache()
        client = Discogs(token="t", cache=cache)
        monkeypatch.setattr(client._http_client, "close", _interrupted)
        with pytest.raises(KeyboardInterrupt):
            client.close()
        assert cache.closed is False
        monkeypatch.undo()
        client._http_client.close()


class TestCredentialPrecedence:
    """Precedence is proven by what reaches the wire and whose identity comes back."""

    def test_explicit_token_beats_environment_oauth(self, monkeypatch):
        monkeypatch.setenv("DISCOGS_CONSUMER_KEY", "env-key")
        monkeypatch.setenv("DISCOGS_CONSUMER_SECRET", "env-secret")
        monkeypatch.setenv("DISCOGS_ACCESS_TOKEN", "env-at")
        monkeypatch.setenv("DISCOGS_ACCESS_TOKEN_SECRET", "env-ats")

        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/oauth/identity").respond(
                200, json=make_identity(username="trent_reznor")
            )
            client = Discogs(token="explicit-token")

            assert client.user.identity().username == "trent_reznor"

            assert (
                route.calls[0].request.headers["Authorization"]
                == "Discogs token=explicit-token"
            )
            client.close()

    def test_explicit_oauth_beats_environment_token(self, monkeypatch):
        monkeypatch.setenv("DISCOGS_TOKEN", "env-token")

        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/oauth/identity").respond(
                200, json=make_identity(username="atticus_ross")
            )
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

            assert (
                route.calls[0].request.headers["Authorization"]
                == "Discogs key=ck, secret=cs"
            )
            client.close()


class TestMaxRetriesValidation:
    @pytest.mark.parametrize("value", [-1, -100])
    def test_negative_max_retries_rejected(self, value):
        with pytest.raises(ValueError, match="max_retries"):
            Discogs(token="t", max_retries=value)

    def test_zero_sends_a_failing_get_once(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").respond(503)
            client = Discogs(token="t", max_retries=0)

            with pytest.raises(DiscogsAPIError):
                client._send("GET", f"{BASE_URL}/releases/352665")

            assert route.call_count == 1
            client.close()
