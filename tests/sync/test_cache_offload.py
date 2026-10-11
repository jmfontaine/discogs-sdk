"""The sync client calls the cache on the calling thread, with the same results.

Twin of tests/async/test_cache_offload.py, where the async client moves the same
calls to worker threads.
"""

from __future__ import annotations

import threading
from contextvars import ContextVar

import pytest

from discogs_sdk import CacheMissError, Discogs, MemoryCache, RequestEvent
from tests.conftest import make_collection_folder, make_release, mock_router

_TRACE: ContextVar[str] = ContextVar("trace", default="unset")
_FOLDER = "/users/trent_reznor/collection/folders/3"


class ThreadRecordingCache(MemoryCache):
    """A ``MemoryCache`` noting the thread and the ``_TRACE`` value of each call."""

    def __init__(self) -> None:
        super().__init__(ttl=600)
        self.calls: list[tuple[str, int, str]] = []

    def _record(self, op: str) -> None:
        self.calls.append((op, threading.get_ident(), _TRACE.get()))

    def get(self, key: str):
        self._record("get")
        return super().get(key)

    def set(
        self, key: str, status_code: int, headers: dict[str, str], body: bytes
    ) -> None:
        self._record("set")
        super().set(key, status_code, headers, body)

    def clear(self) -> None:
        self._record("clear")
        super().clear()

    def ops(self) -> list[str]:
        return [op for op, _, _ in self.calls]


@pytest.fixture
def router():
    with mock_router() as router:
        yield router


class TestCacheCallsStayOnTheCallingThread:
    def test_lookup_store_and_clear_run_on_the_calling_thread(self, router):
        router.get("/releases/352665").respond(200, json=make_release())
        router.post(_FOLDER).respond(200, json=make_collection_folder())
        cache = ThreadRecordingCache()
        client = Discogs(token="t", cache=cache)
        _ = client.releases.get(352665).title  # miss, then store
        _ = client.releases.get(352665).title  # hit
        # A write clears the cache.
        client.users.get("trent_reznor").collection.folders.update(3, name="Halo")
        client.close()
        assert cache.ops() == ["get", "set", "get", "clear"]
        assert {thread for _, thread, _ in cache.calls} == {threading.get_ident()}

    def test_cache_calls_see_the_callers_context(self, router):
        router.get("/releases/352665").respond(200, json=make_release())
        cache = ThreadRecordingCache()
        client = Discogs(token="t", cache=cache)
        token = _TRACE.set("request-1")
        try:
            _ = client.releases.get(352665).title
            _ = client.releases.get(352665).title
        finally:
            _TRACE.reset(token)
        client.close()
        assert [trace for _, _, trace in cache.calls] == ["request-1"] * 3

    def test_no_cache_bypasses_the_cache(self, router):
        route = router.get("/releases/352665").respond(200, json=make_release())
        cache = ThreadRecordingCache()
        client = Discogs(token="t", cache=cache)
        _ = client.releases.get(352665).title
        with client.no_cache():
            _ = client.releases.get(352665).title
        client.close()
        assert route.call_count == 2
        assert cache.ops() == ["get", "set"]

    def test_cache_only_serves_only_from_the_cache(self, router):
        route = router.get("/releases/352665").respond(200, json=make_release())
        cache = ThreadRecordingCache()
        client = Discogs(token="t", cache=cache)
        _ = client.releases.get(352665).title
        with client.cache_only():
            title = client.releases.get(352665).title
            with pytest.raises(CacheMissError):
                _ = client.masters.get(3719).title
        client.close()
        assert title == "The Downward Spiral"
        assert route.call_count == 1
        assert cache.ops() == ["get", "set", "get", "get"]

    def test_events_follow_the_completed_store(self, router):
        router.get("/releases/352665").respond(200, json=make_release())
        cache = ThreadRecordingCache()
        seen: list[tuple[str, bool, list[str]]] = []

        def on_request(event: RequestEvent) -> None:
            seen.append((event.source, event.stored, cache.ops()))

        client = Discogs(token="t", cache=cache, on_request=on_request)
        _ = client.releases.get(352665).title
        _ = client.releases.get(352665).title
        client.close()
        assert seen == [
            ("network", True, ["get", "set"]),
            ("cache", False, ["get", "set", "get"]),
        ]
