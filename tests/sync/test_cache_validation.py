"""A cached body is validated before it is stored and on every hit (#175)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pydantic
import pytest
import respx

from discogs_sdk import (
    CacheEntry,
    CacheMissError,
    Discogs,
    MemoryCache,
    ResponseCache,
    SQLiteCache,
)
from tests.conftest import (
    cache_key,
    exclusive_lock,
    make_artist_release,
    make_collection_folder,
    make_identity,
    make_paginated_response,
    make_release,
    mock_router,
    seed_cache,
)


def _release(client: Discogs) -> Any:
    return client.releases.get(352665).title


def _folders(client: Discogs) -> Any:
    folders = client.users.get("trent_reznor").collection.folders.list()
    return [f.name for f in folders]


def _page(client: Discogs) -> Any:
    return [r.title for r in client.artists.get(3857).releases.list()]


def _identity(client: Discogs) -> Any:
    return client.user.identity().username


@dataclass(frozen=True)
class Endpoint:
    path: str
    params: dict[str, Any] | None
    valid: dict[str, Any]
    invalid: dict[str, Any]
    call: Callable[[Discogs], Any]
    expected: Any


ENDPOINTS = {
    "lazy": Endpoint(
        "/releases/352665",
        None,
        make_release(),
        {"id": "not a number", "title": "The Downward Spiral"},
        _release,
        "The Downward Spiral",
    ),
    "list": Endpoint(
        "/users/trent_reznor/collection/folders",
        None,
        {"folders": [make_collection_folder()]},
        {"folders": [{"id": "not a number", "name": "All"}]},
        _folders,
        ["All"],
    ),
    "page": Endpoint(
        "/artists/3857/releases",
        {"page": 1},
        make_paginated_response("releases", [make_artist_release()]),
        make_paginated_response("releases", [{"id": "not a number"}]),
        _page,
        ["Pretty Hate Machine"],
    ),
    "identity": Endpoint(
        "/oauth/identity",
        None,
        make_identity(),
        {"id": "not a number", "username": "trent_reznor"},
        _identity,
        "trent_reznor",
    ),
}


@pytest.fixture(params=list(ENDPOINTS))
def endpoint(request) -> Endpoint:
    return ENDPOINTS[request.param]


@pytest.fixture(params=["memory", "sqlite"])
def backend(request, tmp_path):
    cache = (
        MemoryCache(ttl=600)
        if request.param == "memory"
        else SQLiteCache(ttl=600, cache_dir=tmp_path)
    )
    yield cache
    cache.close()


class NoDeleteCache(ResponseCache):
    """A third-party backend written before ``delete`` existed."""

    def __init__(self) -> None:
        super().__init__(ttl=0)
        self.store: dict[str, CacheEntry] = {}

    def get(self, key: str) -> CacheEntry | None:
        return self.store.get(key)

    def set(
        self, key: str, status_code: int, headers: dict[str, str], body: bytes
    ) -> None:
        self.store[key] = (status_code, headers, body)

    def clear(self) -> None:
        self.store.clear()

    def close(self) -> None:
        pass


class RaisingDeleteCache(NoDeleteCache):
    def delete(self, key: str) -> None:
        raise RuntimeError("backend is down")


def _body(cache: ResponseCache, key: str) -> Any:
    entry = cache.get(key)
    return None if entry is None else json.loads(entry[2])


class TestFreshBodies:
    def test_invalid_body_raises_and_is_not_stored(self, endpoint, backend):
        events = []
        with mock_router() as router:
            router.get(endpoint.path).respond(200, json=endpoint.invalid)
            client = Discogs(token="t", cache=backend, on_request=events.append)
            with pytest.raises(pydantic.ValidationError):
                endpoint.call(client)
            key = cache_key(client, endpoint.path, params=endpoint.params)
            client.close()
        assert backend.get(key) is None
        assert [(e.source, e.stored) for e in events] == [("network", False)]

    def test_valid_body_is_stored_and_served(self, endpoint, backend):
        events = []
        with mock_router() as router:
            route = router.get(endpoint.path).respond(200, json=endpoint.valid)
            client = Discogs(token="t", cache=backend, on_request=events.append)
            assert endpoint.call(client) == endpoint.expected
            assert endpoint.call(client) == endpoint.expected
            client.close()
        assert route.call_count == 1
        assert [(e.source, e.stored) for e in events] == [
            ("network", True),
            ("cache", False),
        ]


class TestInvalidCacheHits:
    def test_valid_refetch_replaces_the_entry(self, endpoint, backend):
        events = []
        with mock_router() as router:
            route = router.get(endpoint.path).respond(200, json=endpoint.valid)
            client = Discogs(token="t", cache=backend, on_request=events.append)
            key = seed_cache(
                client, backend, endpoint.path, endpoint.invalid, params=endpoint.params
            )
            assert endpoint.call(client) == endpoint.expected
            client.close()
        assert route.call_count == 1
        assert [(e.source, e.attempts, e.stored) for e in events] == [
            ("network", 1, True)
        ]
        assert _body(backend, key) == endpoint.valid

    def test_invalid_refetch_raises_and_drops_the_entry(self, endpoint, backend):
        events = []
        with mock_router() as router:
            route = router.get(endpoint.path).respond(200, json=endpoint.invalid)
            client = Discogs(token="t", cache=backend, on_request=events.append)
            key = seed_cache(
                client, backend, endpoint.path, endpoint.invalid, params=endpoint.params
            )
            with pytest.raises(pydantic.ValidationError):
                endpoint.call(client)
            client.close()
        assert route.call_count == 1
        assert [(e.source, e.stored) for e in events] == [("network", False)]
        assert backend.get(key) is None

    def test_cache_only_raises_a_miss_and_drops_the_entry(
        self, endpoint, backend, caplog
    ):
        caplog.set_level(logging.WARNING, logger="discogs_sdk")
        events = []
        with mock_router(assert_all_called=False) as router:
            route = router.get(endpoint.path).respond(200, json=endpoint.valid)
            client = Discogs(token="t", cache=backend, on_request=events.append)
            key = seed_cache(
                client, backend, endpoint.path, endpoint.invalid, params=endpoint.params
            )
            with client.cache_only(), pytest.raises(CacheMissError):
                endpoint.call(client)
            client.close()
        assert route.call_count == 0
        assert [(e.source, e.status_code, e.attempts) for e in events] == [
            ("miss", None, 0)
        ]
        assert backend.get(key) is None
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_rejected_hit_then_retried_fetch_emits_one_event(self, endpoint, backend):
        events = []
        with mock_router() as router:
            router.get(endpoint.path).mock(
                side_effect=[
                    respx.MockResponse(503),
                    respx.MockResponse(200, json=endpoint.valid),
                ]
            )
            client = Discogs(
                token="t", cache=backend, max_retries=1, on_request=events.append
            )
            seed_cache(
                client, backend, endpoint.path, endpoint.invalid, params=endpoint.params
            )
            with patch("time.sleep"):
                assert endpoint.call(client) == endpoint.expected
            client.close()
        assert [(e.source, e.status_code, e.attempts) for e in events] == [
            ("network", 200, 2)
        ]

    def test_malformed_page_envelope_is_rejected(self, backend):
        endpoint = ENDPOINTS["page"]
        with mock_router() as router:
            route = router.get(endpoint.path).respond(200, json=endpoint.valid)
            client = Discogs(token="t", cache=backend)
            key = seed_cache(
                client, backend, endpoint.path, {"releases": {}}, params=endpoint.params
            )
            assert endpoint.call(client) == endpoint.expected
            client.close()
        assert route.call_count == 1
        assert _body(backend, key) == endpoint.valid

    def test_backend_without_delete_never_serves_the_entry(self, endpoint):
        cache = NoDeleteCache()
        with mock_router(assert_all_called=False) as router:
            route = router.get(endpoint.path).respond(200, json=endpoint.valid)
            client = Discogs(token="t", cache=cache)
            key = seed_cache(
                client, cache, endpoint.path, endpoint.invalid, params=endpoint.params
            )
            for _ in range(3):
                with client.cache_only(), pytest.raises(CacheMissError):
                    endpoint.call(client)
            assert route.call_count == 0
            assert _body(cache, key) == endpoint.invalid
            assert endpoint.call(client) == endpoint.expected
            client.close()
        assert route.call_count == 1
        assert _body(cache, key) == endpoint.valid


class TestFailingDelete:
    def test_failed_delete_is_logged_and_the_call_refetches(
        self, tmp_path, caplog, fast_sqlite_busy_timeout
    ):
        cache = SQLiteCache(ttl=600, cache_dir=tmp_path)
        endpoint = ENDPOINTS["lazy"]
        caplog.set_level(logging.WARNING, logger="discogs_sdk")
        with mock_router() as router:
            route = router.get(endpoint.path).respond(200, json=endpoint.valid)
            client = Discogs(token="t", cache=cache)
            seed_cache(client, cache, endpoint.path, endpoint.invalid)
            with exclusive_lock(tmp_path):
                assert endpoint.call(client) == endpoint.expected
            client.close()
        cache.close()
        assert route.call_count == 1
        assert any(
            r.levelno == logging.WARNING
            and "could not delete an entry: database is locked" in r.getMessage()
            for r in caplog.records
        )

    def test_failed_delete_under_cache_only_raises_a_miss(
        self, tmp_path, caplog, fast_sqlite_busy_timeout
    ):
        cache = SQLiteCache(ttl=600, cache_dir=tmp_path)
        endpoint = ENDPOINTS["lazy"]
        caplog.set_level(logging.WARNING, logger="discogs_sdk")
        with mock_router(assert_all_called=False) as router:
            route = router.get(endpoint.path).respond(200, json=endpoint.valid)
            client = Discogs(token="t", cache=cache)
            seed_cache(client, cache, endpoint.path, endpoint.invalid)
            with (
                exclusive_lock(tmp_path),
                client.cache_only(),
                pytest.raises(CacheMissError),
            ):
                endpoint.call(client)
            client.close()
        cache.close()
        assert route.call_count == 0
        assert any(
            r.levelno == logging.WARNING and "database is locked" in r.getMessage()
            for r in caplog.records
        )

    def test_raising_delete_is_logged_and_ignored(self, caplog):
        cache = RaisingDeleteCache()
        endpoint = ENDPOINTS["lazy"]
        caplog.set_level(logging.WARNING, logger="discogs_sdk")
        with mock_router() as router:
            route = router.get(endpoint.path).respond(200, json=endpoint.valid)
            client = Discogs(token="t", cache=cache)
            seed_cache(client, cache, endpoint.path, endpoint.invalid)
            assert endpoint.call(client) == endpoint.expected
            client.close()
        assert route.call_count == 1
        assert any(
            r.levelno == logging.WARNING and "backend is down" in r.getMessage()
            for r in caplog.records
        )


class TestPageStaysPut:
    def test_rejected_page_leaves_the_paginator_unchanged(self, backend):
        endpoint = ENDPOINTS["page"]
        with mock_router() as router:
            route = router.get(endpoint.path).mock(
                side_effect=[
                    respx.MockResponse(200, json=endpoint.invalid),
                    respx.MockResponse(200, json=endpoint.valid),
                ]
            )
            client = Discogs(token="t", cache=backend)
            seed_cache(
                client, backend, endpoint.path, endpoint.invalid, params=endpoint.params
            )
            page = client.artists.get(3857).releases.list()
            with pytest.raises(pydantic.ValidationError):
                next(page)
            assert page.page is None
            assert page.total_items is None
            assert [r.title for r in page] == ["Pretty Hate Machine"]
            client.close()
        assert route.call_count == 2
