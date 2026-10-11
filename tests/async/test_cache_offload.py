"""The async client runs blocking cache and file I/O off the event loop."""

from __future__ import annotations

import asyncio
import threading
import time
from contextvars import ContextVar
from pathlib import Path
from unittest.mock import patch

import pytest
import respx

from discogs_sdk import AsyncDiscogs, CacheMissError, MemoryCache, RequestEvent
from tests.conftest import BASE_URL, make_collection_folder, make_release

_TRACE: ContextVar[str] = ContextVar("trace", default="unset")
_FOLDER = "/users/trent_reznor/collection/folders/3"


class ThreadRecordingCache(MemoryCache):
    """A ``MemoryCache`` noting the thread and the ``_TRACE`` value of each call."""

    def __init__(self, *, get_delay: float = 0.0) -> None:
        super().__init__(ttl=600)
        self.get_delay = get_delay
        self.calls: list[tuple[str, int, str]] = []

    def _record(self, op: str) -> None:
        self.calls.append((op, threading.get_ident(), _TRACE.get()))

    def get(self, key: str):
        self._record("get")
        time.sleep(self.get_delay)
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
    with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
        yield router


class TestCacheCallsLeaveTheLoop:
    async def test_lookup_store_and_clear_run_on_worker_threads(self, router):
        router.get("/releases/352665").respond(200, json=make_release())
        router.post(_FOLDER).respond(200, json=make_collection_folder())
        cache = ThreadRecordingCache()
        client = AsyncDiscogs(token="t", cache=cache)
        await client.releases.get(352665)  # miss, then store
        await client.releases.get(352665)  # hit
        # A write clears the cache.
        await client.users.get("trent_reznor").collection.folders.update(3, name="Halo")
        await client.close()
        loop_thread = threading.get_ident()
        assert cache.ops() == ["get", "set", "get", "clear"]
        assert all(thread != loop_thread for _, thread, _ in cache.calls)

    async def test_cache_calls_see_the_callers_context(self, router):
        router.get("/releases/352665").respond(200, json=make_release())
        cache = ThreadRecordingCache()
        client = AsyncDiscogs(token="t", cache=cache)
        _TRACE.set("request-1")
        await client.releases.get(352665)
        await client.releases.get(352665)
        await client.close()
        assert [trace for _, _, trace in cache.calls] == ["request-1"] * 3

    async def test_no_cache_still_bypasses_the_cache(self, router):
        route = router.get("/releases/352665").respond(200, json=make_release())
        cache = ThreadRecordingCache()
        client = AsyncDiscogs(token="t", cache=cache)
        await client.releases.get(352665)
        async with client.no_cache():
            await client.releases.get(352665)
        await client.close()
        assert route.call_count == 2
        assert cache.ops() == ["get", "set"]

    async def test_cache_only_still_serves_only_from_the_cache(self, router):
        route = router.get("/releases/352665").respond(200, json=make_release())
        cache = ThreadRecordingCache()
        client = AsyncDiscogs(token="t", cache=cache)
        await client.releases.get(352665)
        async with client.cache_only():
            release = await client.releases.get(352665)
            with pytest.raises(CacheMissError):
                await client.masters.get(3719)
        await client.close()
        assert release.title == "The Downward Spiral"
        assert route.call_count == 1
        assert cache.ops() == ["get", "set", "get", "get"]

    async def test_events_follow_the_completed_store(self, router):
        router.get("/releases/352665").respond(200, json=make_release())
        cache = ThreadRecordingCache()
        seen: list[tuple[str, bool, list[str]]] = []

        def on_request(event: RequestEvent) -> None:
            seen.append((event.source, event.stored, cache.ops()))

        client = AsyncDiscogs(token="t", cache=cache, on_request=on_request)
        await client.releases.get(352665)
        await client.releases.get(352665)
        await client.close()
        assert seen == [
            ("network", True, ["get", "set"]),
            ("cache", False, ["get", "set", "get"]),
        ]

    async def test_slow_lookup_does_not_stall_other_tasks(self, router):
        router.get("/releases/352665").respond(200, json=make_release())
        client = AsyncDiscogs(token="t", cache=ThreadRecordingCache(get_delay=0.2))
        ticks = 0

        async def ticker() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        task = asyncio.create_task(ticker())
        await asyncio.sleep(0)  # let the ticker start
        await client.releases.get(352665)
        task.cancel()
        await client.close()
        # 0.2s of lookup leaves room for ~20 ticks; a blocked loop allows none.
        assert ticks >= 5


class TestUploadFileRead:
    async def test_file_is_read_on_a_worker_thread(self, router, tmp_path):
        router.post("/inventory/upload/add").respond(200)
        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text("release_id,price\n352665,25.00\n")
        threads: list[int] = []
        read_bytes = Path.read_bytes

        def recording_read_bytes(self: Path) -> bytes:
            threads.append(threading.get_ident())
            return read_bytes(self)

        client = AsyncDiscogs(token="t")
        with patch.object(Path, "read_bytes", recording_read_bytes):
            await client.uploads.create(file=csv_file)
        await client.close()
        assert len(threads) == 1
        assert threads[0] != threading.get_ident()
