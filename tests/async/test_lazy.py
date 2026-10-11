"""Tests for AsyncLazyResource."""

from __future__ import annotations

import asyncio
import gc

import pytest
import respx

from discogs_sdk._async.resources.artists import ArtistReleases
from discogs_sdk._async.resources.releases import ReleaseRating, ReleaseStatsResource
from discogs_sdk._exceptions import NotFoundError
from discogs_sdk.models.release import Release
from tests.conftest import make_release


class TestCreation:
    def test_no_http_on_creation(self, client, respx_mock):
        _lazy = client.releases.get(400027)
        assert respx_mock.calls.call_count == 0

    def test_repr_before_resolve(self, client):
        lazy = client.releases.get(400027)
        r = repr(lazy)
        assert "AsyncLazyResource" in r
        assert "Release" in r
        assert "/releases/400027" in r


class TestResolve:
    async def test_await_triggers_http(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        lazy = client.releases.get(400027)
        result = await lazy
        assert isinstance(result, Release)
        assert result.id == 400027
        assert result.title == "The Downward Spiral"
        assert respx_mock.calls.call_count == 1

    async def test_second_await_cached(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        lazy = client.releases.get(400027)
        await lazy
        await lazy
        assert respx_mock.calls.call_count == 1

    async def test_repr_after_resolve(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        lazy = client.releases.get(400027)
        await lazy
        r = repr(lazy)
        assert "AsyncLazyResource" not in r

    async def test_error_raises(self, client, respx_mock):
        respx_mock.get("/releases/999").mock(
            return_value=respx.MockResponse(404, json={"message": "Not Found"})
        )
        lazy = client.releases.get(999)
        with pytest.raises(NotFoundError):
            await lazy


class TestConcurrentAwaits:
    """Independent tasks awaiting one unresolved proxy share a single request.

    The route parks every request on *gate*, so all awaiters are waiting before
    any response arrives; ``asyncio.gather(lazy, lazy)`` would not show this, since
    it de-duplicates identical awaitables.
    """

    @staticmethod
    def park(respx_mock, response):
        entered = asyncio.Event()
        gate = asyncio.Event()

        async def handler(request):
            entered.set()
            await gate.wait()
            return response

        route = respx_mock.get("/releases/352665").mock(side_effect=handler)
        return route, entered, gate

    @staticmethod
    async def start(lazy, count=3):
        async def wait_for(proxy):
            return await proxy

        tasks = [asyncio.create_task(wait_for(lazy)) for _ in range(count)]
        # One more turn after the request starts, so every task is parked on it.
        await asyncio.sleep(0)
        return tasks

    @staticmethod
    async def settle():
        # The fetch outlives its waiters: wait for every other task on the loop.
        # asyncio.wait() starts no task of its own, unlike wait_for() before 3.12.
        others = asyncio.all_tasks() - {asyncio.current_task()}
        if others:
            _, pending = await asyncio.wait(others, timeout=1)
            assert not pending

    async def test_three_awaiters_send_one_request(self, client, respx_mock):
        route, entered, gate = self.park(
            respx_mock, respx.MockResponse(200, json=make_release(id=352665))
        )
        lazy = client.releases.get(352665)
        tasks = await self.start(lazy)
        await entered.wait()
        gate.set()
        first, second, third = await asyncio.gather(*tasks)
        assert isinstance(first, Release)
        assert first is second is third
        assert route.call_count == 1
        assert await lazy is first
        assert route.call_count == 1

    async def test_failure_reaches_every_awaiter_and_is_not_cached(
        self, client, respx_mock
    ):
        route, entered, gate = self.park(
            respx_mock, respx.MockResponse(404, json={"message": "Not Found"})
        )
        lazy = client.releases.get(352665)
        tasks = await self.start(lazy)
        await entered.wait()
        gate.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(isinstance(result, NotFoundError) for result in results)
        assert route.call_count == 1

        route.mock(
            side_effect=None,
            return_value=respx.MockResponse(200, json=make_release(id=352665)),
        )
        release = await lazy
        assert release.id == 352665
        assert route.call_count == 2

    async def test_failed_fetch_is_not_replayed_before_its_slot_clears(
        self, client, respx_mock
    ):
        # A task already queued when the fetch fails runs before the fetch's done
        # callback clears the slot; it must start a request, not get the failure.
        route = respx_mock.get("/releases/352665").mock(
            return_value=respx.MockResponse(200, json=make_release(id=352665))
        )

        async def failed():
            raise RuntimeError("stale failure")

        stale = asyncio.create_task(failed())
        await asyncio.gather(stale, return_exceptions=True)
        lazy = client.releases.get(352665)
        object.__setattr__(lazy, "_inflight", stale)
        release = await lazy
        assert release.id == 352665
        assert route.call_count == 1

    async def test_cancelling_one_awaiter_leaves_the_others(self, client, respx_mock):
        route, entered, gate = self.park(
            respx_mock, respx.MockResponse(200, json=make_release(id=352665))
        )
        lazy = client.releases.get(352665)
        tasks = await self.start(lazy)
        await entered.wait()
        # The first task is the one that started the request.
        tasks[0].cancel()
        gate.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert isinstance(results[0], asyncio.CancelledError)
        assert results[1] is results[2]
        assert isinstance(results[1], Release)
        assert route.call_count == 1

    async def test_request_outlives_cancelling_every_awaiter(self, client, respx_mock):
        route, entered, gate = self.park(
            respx_mock, respx.MockResponse(200, json=make_release(id=352665))
        )
        lazy = client.releases.get(352665)
        tasks = await self.start(lazy)
        await entered.wait()
        for task in tasks:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(isinstance(result, asyncio.CancelledError) for result in results)
        gate.set()
        await self.settle()
        assert "AsyncLazyResource" not in repr(lazy)
        release = await lazy
        assert release.id == 352665
        assert route.call_count == 1

    async def test_unawaited_failure_is_not_reported_as_unretrieved(
        self, client, respx_mock
    ):
        route, entered, gate = self.park(
            respx_mock, respx.MockResponse(404, json={"message": "Not Found"})
        )
        lazy = client.releases.get(352665)

        async def cancel_every_awaiter():
            # In a frame of its own: a cancelled waiter's traceback keeps the
            # request alive, and the unretrieved report only fires once it is freed.
            tasks = await self.start(lazy)
            await entered.wait()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        loop = asyncio.get_running_loop()
        reported = []
        loop.set_exception_handler(lambda _loop, context: reported.append(context))
        try:
            await cancel_every_awaiter()
            gate.set()
            await self.settle()
            gc.collect()
        finally:
            loop.set_exception_handler(None)
        assert reported == []
        with pytest.raises(NotFoundError):
            await lazy
        assert route.call_count == 2


class TestAttributeAccess:
    async def test_data_attr_before_await_raises(self, client):
        lazy = client.releases.get(400027)
        with pytest.raises(AttributeError, match="Cannot access 'title'"):
            _ = lazy.title

    async def test_data_attr_after_await(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        lazy = client.releases.get(400027)
        await lazy
        assert lazy.title == "The Downward Spiral"


class TestGetItem:
    def test_getitem_before_await_raises(self, client):
        lazy = client.releases.get(400027)
        with pytest.raises(TypeError, match="Cannot subscript unresolved"):
            lazy["title"]

    async def test_getitem_after_await(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        lazy = client.releases.get(400027)
        await lazy
        # Pydantic models don't support subscript by default, so this should raise
        with pytest.raises(TypeError, match="not subscriptable"):
            lazy["title"]


class TestSubResources:
    def test_sub_resource_no_http(self, client, respx_mock):
        lazy = client.releases.get(400027)
        _rating = lazy.rating
        assert respx_mock.calls.call_count == 0

    def test_sub_resource_cached(self, client):
        lazy = client.releases.get(400027)
        r1 = lazy.rating
        r2 = lazy.rating
        assert r1 is r2

    def test_multiple_sub_resources(self, client, respx_mock):
        lazy = client.releases.get(400027)
        _ = lazy.rating
        _ = lazy.stats
        _ = lazy.price_suggestions
        _ = lazy.marketplace_stats
        assert respx_mock.calls.call_count == 0


class TestReadOnly:
    async def test_field_assignment_raises_before_any_request(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        lazy = client.releases.get(400027)
        with pytest.raises(AttributeError, match="'title'.*read-only"):
            lazy.title = "x"
        assert respx_mock.calls.call_count == 0
        await lazy
        assert lazy.title == "The Downward Spiral"

    async def test_field_assignment_raises_after_await(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        lazy = client.releases.get(400027)
        await lazy
        with pytest.raises(AttributeError, match="'title'.*read-only"):
            lazy.title = "x"
        assert lazy.title == "The Downward Spiral"

    def test_sub_resource_assignment_raises(self, client):
        artist = client.artists.get(3857)
        with pytest.raises(AttributeError, match="'releases'.*read-only"):
            artist.releases = None
        release = client.releases.get(400027)
        rating = release.rating
        with pytest.raises(AttributeError, match="'rating'.*read-only"):
            release.rating = None
        assert release.rating is rating


class TestTypedSurface:
    async def test_await_returns_the_concrete_model(self, client, respx_mock):
        respx_mock.get("/releases/400027").mock(
            return_value=respx.MockResponse(200, json=make_release())
        )
        resolved = await client.releases.get(400027)
        assert isinstance(resolved, Release)

    def test_sub_resources_are_concrete_resources(self, client, respx_mock):
        lazy = client.releases.get(400027)
        assert isinstance(lazy.rating, ReleaseRating)
        assert isinstance(lazy.stats, ReleaseStatsResource)
        assert isinstance(client.artists.get(3857).releases, ArtistReleases)
        assert respx_mock.calls.call_count == 0

    def test_deep_navigation_makes_no_request(self, client, respx_mock):
        instance = (
            client.users.get("trent_reznor")
            .collection.folders.get(1)
            .releases.get(352665)
            .instances.get(20)
        )
        assert instance.fields is not None
        assert respx_mock.calls.call_count == 0
