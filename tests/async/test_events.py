"""Tests for request events, the rate-limit budget and cache-only mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx2
import pytest
import respx

from discogs_sdk import (
    AsyncDiscogs,
    CacheMissError,
    DiscogsConnectionError,
    RateLimit,
    RateLimitError,
    RequestEvent,
)
from tests.conftest import BASE_URL, make_release

RATELIMIT_HEADERS = {
    "X-Discogs-Ratelimit": "60",
    "X-Discogs-Ratelimit-Used": "14",
    "X-Discogs-Ratelimit-Remaining": "46",
}


def _ok(headers: dict[str, str] | None = None) -> respx.MockResponse:
    return respx.MockResponse(200, json=make_release(), headers=headers)


class TestRequestEvents:
    async def test_network_event_fields(self):
        events: list[RequestEvent] = []
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/releases/352665").mock(return_value=_ok(RATELIMIT_HEADERS))
            client = AsyncDiscogs(token="t", on_request=events.append)
            await client._send(
                "get", f"{BASE_URL}/releases/352665", params={"curr_abbr": "USD"}
            )
            await client.close()

        assert len(events) == 1
        event = events[0]
        assert event.method == "GET"
        assert event.url == f"{BASE_URL}/releases/352665?curr_abbr=USD"
        assert event.status_code == 200
        assert event.source == "network"
        assert event.attempts == 1
        assert event.stored is False
        assert event.ratelimit == RateLimit(60, 14, 46)
        assert event.elapsed_ms >= 0
        assert client.ratelimit == RateLimit(60, 14, 46)

    async def test_cache_hit_event(self):
        events: list[RequestEvent] = []
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").mock(
                return_value=_ok(RATELIMIT_HEADERS)
            )
            client = AsyncDiscogs(token="t", cache=True, on_request=events.append)
            await client._send("GET", f"{BASE_URL}/releases/352665")
            await client._send("GET", f"{BASE_URL}/releases/352665")
            await client.close()

        assert route.call_count == 1
        network, hit = events
        assert network.source == "network"
        assert network.stored is True
        assert hit.source == "cache"
        assert hit.attempts == 0
        assert hit.stored is False
        assert hit.ratelimit is None
        assert hit.url == f"{BASE_URL}/releases/352665"
        assert hit.status_code == 200
        assert client.ratelimit == RateLimit(60, 14, 46)

    async def test_ratelimit_keeps_last_known_when_headers_absent(self):
        events: list[RequestEvent] = []
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/releases/352665").mock(
                side_effect=[_ok(RATELIMIT_HEADERS), _ok()]
            )
            client = AsyncDiscogs(token="t", on_request=events.append)
            await client._send("GET", f"{BASE_URL}/releases/352665")
            await client._send("GET", f"{BASE_URL}/releases/352665")
            await client.close()

        assert events[1].ratelimit is None
        assert client.ratelimit == RateLimit(60, 14, 46)

    async def test_ratelimit_error_carries_headers(self):
        events: list[RequestEvent] = []
        headers = {**RATELIMIT_HEADERS, "Retry-After": "17"}
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/releases/352665").mock(
                return_value=respx.MockResponse(
                    429, json={"message": "slow down"}, headers=headers
                )
            )
            client = AsyncDiscogs(token="t", max_retries=0, on_request=events.append)
            with pytest.raises(RateLimitError) as exc_info:
                await client._send("GET", f"{BASE_URL}/releases/352665")
            await client.close()

        assert exc_info.value.ratelimit == RateLimit(60, 14, 46)
        assert exc_info.value.retry_after == "17"
        assert [e.status_code for e in events] == [429]
        assert client.ratelimit == RateLimit(60, 14, 46)

    async def test_retries_produce_one_event_with_attempts(self):
        events: list[RequestEvent] = []
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/releases/352665").mock(
                side_effect=[respx.MockResponse(503), _ok()]
            )
            client = AsyncDiscogs(token="t", max_retries=1, on_request=events.append)
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await client._send("GET", f"{BASE_URL}/releases/352665")
            await client.close()

        assert len(events) == 1
        assert events[0].attempts == 2
        assert events[0].status_code == 200

    async def test_connection_error_emits_no_event(self):
        events: list[RequestEvent] = []
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/releases/352665").mock(
                side_effect=httpx2.ConnectError("refused")
            )
            client = AsyncDiscogs(token="t", max_retries=0, on_request=events.append)
            with pytest.raises(DiscogsConnectionError):
                await client._send("GET", f"{BASE_URL}/releases/352665")
            await client.close()

        assert events == []
        assert client.ratelimit is None

    async def test_callback_exception_propagates(self):
        def boom(event: RequestEvent) -> None:
            raise RuntimeError("observer failed")

        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/releases/352665").mock(return_value=_ok())
            client = AsyncDiscogs(token="t", on_request=boom)
            with pytest.raises(RuntimeError, match="observer failed"):
                await client._send("GET", f"{BASE_URL}/releases/352665")
            await client.close()


class TestCacheOnly:
    async def test_cache_only_miss_raises_before_network(self):
        events: list[RequestEvent] = []
        with respx.mock(
            base_url=BASE_URL, using="httpcore2", assert_all_called=False
        ) as router:
            route = router.get("/releases/352665").mock(return_value=_ok())
            client = AsyncDiscogs(token="t", cache=True, on_request=events.append)
            async with client.cache_only():
                with pytest.raises(CacheMissError) as exc_info:
                    await client._send(
                        "get", f"{BASE_URL}/releases/352665", params={"x": "1"}
                    )
            await client.close()

        assert route.call_count == 0
        assert events == []
        assert exc_info.value.method == "GET"
        assert exc_info.value.url == f"{BASE_URL}/releases/352665?x=1"

    async def test_cache_only_hit_serves_from_cache(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").mock(return_value=_ok())
            client = AsyncDiscogs(token="t", cache=True)
            await client._send("GET", f"{BASE_URL}/releases/352665")
            async with client.cache_only():
                response = await client._send("GET", f"{BASE_URL}/releases/352665")
            await client.close()

        assert route.call_count == 1
        assert response.json()["id"] == make_release()["id"]

    async def test_cache_only_with_cache_disabled_raises(self):
        with respx.mock(
            base_url=BASE_URL, using="httpcore2", assert_all_called=False
        ) as router:
            route = router.get("/releases/352665").mock(return_value=_ok())
            client = AsyncDiscogs(token="t", cache=False)
            async with client.cache_only():
                with pytest.raises(CacheMissError):
                    await client._send("GET", f"{BASE_URL}/releases/352665")
            await client.close()

        assert route.call_count == 0

    async def test_cache_only_inside_no_cache_raises(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").mock(return_value=_ok())
            client = AsyncDiscogs(token="t", cache=True)
            await client._send("GET", f"{BASE_URL}/releases/352665")
            async with client.no_cache(), client.cache_only():
                with pytest.raises(CacheMissError):
                    await client._send("GET", f"{BASE_URL}/releases/352665")
            await client.close()

        assert route.call_count == 1

    async def test_cache_only_scope_restores(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.get("/releases/352665").mock(return_value=_ok())
            client = AsyncDiscogs(token="t", cache=True)
            async with client.cache_only():
                with pytest.raises(CacheMissError):
                    await client._send("GET", f"{BASE_URL}/releases/352665")
            await client._send("GET", f"{BASE_URL}/releases/352665")
            assert route.call_count == 1

            with pytest.raises(RuntimeError):
                async with client.cache_only():
                    raise RuntimeError("boom")
            async with client.no_cache():
                await client._send("GET", f"{BASE_URL}/releases/352665")
            assert route.call_count == 2
            await client.close()

    async def test_cache_only_non_get_raises(self):
        with respx.mock(
            base_url=BASE_URL, using="httpcore2", assert_all_called=False
        ) as router:
            route = router.post("/users/trent_reznor/wants/352665").mock(
                return_value=_ok()
            )
            client = AsyncDiscogs(token="t", cache=True)
            async with client.cache_only():
                with pytest.raises(CacheMissError) as exc_info:
                    await client._send(
                        "POST", f"{BASE_URL}/users/trent_reznor/wants/352665"
                    )
            await client.close()

        assert route.call_count == 0
        assert exc_info.value.method == "POST"
