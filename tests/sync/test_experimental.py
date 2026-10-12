"""releases_added_since() scans the undocumented date_added sort and verifies each date (#192)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import respx

from discogs_sdk import Discogs, DiscogsError, RequestEvent
from discogs_sdk.experimental import releases_added_since
from tests.conftest import (
    BASE_URL,
    make_paginated_response,
    make_release,
    make_search_result,
)

CUTOFF = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _added(days: float) -> str:
    """``date_added`` as Discogs sends it, *days* after the cutoff."""
    return (CUTOFF + timedelta(days=days)).isoformat()


# Two pages, newest first; release 6 is the first one added before the cutoff.
TWO_PAGES = [
    [(1, _added(5)), (2, _added(4)), (3, _added(3))],
    [(4, _added(2)), (5, _added(0)), (6, _added(-1)), (7, _added(-2))],
]


class _Discogs:
    """A mocked /database/search and /releases/{id}, answering by page and id."""

    def __init__(
        self,
        router: respx.MockRouter,
        pages: Sequence[Sequence[tuple[int, str | None]]],
        *,
        failures: dict[int, int] | None = None,
    ) -> None:
        self.pages = pages
        self.dates = {rid: added for page in pages for rid, added in page}
        # Release id -> how many 503s to answer before the 200.
        self.failures = dict(failures or {})
        self.search = router.get("/database/search").mock(side_effect=self._search)
        # The strict router fails a route that is never called, and an empty
        # search needs no lookup.
        if self.dates:
            self.lookup = router.get(path__regex=r"^/releases/(?P<rid>\d+)$").mock(
                side_effect=self._lookup
            )

    def _search(self, request):
        page = int(request.url.params["page"])
        items = self.pages[page - 1] if page <= len(self.pages) else []
        body = make_paginated_response(
            "results",
            [make_search_result(id=rid) for rid, _ in items],
            page=page,
            pages=len(self.pages),
            next_url=(
                f"{BASE_URL}/database/search?page={page + 1}"
                if page < len(self.pages)
                else None
            ),
        )
        return respx.MockResponse(200, json=body)

    def _lookup(self, request, rid):
        rid = int(rid)
        if self.failures.get(rid):
            self.failures[rid] -= 1
            return respx.MockResponse(503)
        body = make_release(id=rid)
        if self.dates[rid] is not None:
            body["date_added"] = self.dates[rid]
        return respx.MockResponse(200, json=body)

    def looked_up(self) -> list[int]:
        return [
            int(call.request.url.path.rsplit("/", 1)[1]) for call in self.lookup.calls
        ]


def _sends(events: list[RequestEvent]) -> int:
    return sum(e.attempts for e in events if e.source == "network")


@pytest.fixture
def events() -> list[RequestEvent]:
    return []


@pytest.fixture
def no_retry_client(respx_mock, events):
    return Discogs(token="test-token", max_retries=0, on_request=events.append)


class TestScan:
    def test_returns_the_window_newest_first_at_the_documented_cost(
        self, no_retry_client, respx_mock, events
    ):
        api = _Discogs(respx_mock, TWO_PAGES)

        result = releases_added_since(no_retry_client, CUTOFF, artist="Nine Inch Nails")

        assert [r.id for r in result.releases] == [1, 2, 3, 4, 5]
        assert [r.date_added for r in result.releases] == [
            datetime.fromisoformat(_added(d)) for d in (5, 4, 3, 2, 0)
        ]
        assert result.complete is True
        # Two pages, five releases in the window, plus the one that ends the scan.
        assert _sends(events) == 2 + 5 + 1
        assert api.looked_up() == [1, 2, 3, 4, 5, 6]
        params = api.search.calls.last.request.url.params
        assert params["type"] == "release"
        assert params["sort"] == "date_added"
        assert params["sort_order"] == "desc"
        assert params["artist"] == "Nine Inch Nails"

    def test_a_date_means_the_start_of_that_day_in_utc(
        self, no_retry_client, respx_mock
    ):
        _Discogs(
            respx_mock,
            [[(1, "2026-10-01T00:00:00+00:00"), (2, "2026-09-30T23:59:59+00:00")]],
        )

        result = releases_added_since(no_retry_client, date(2026, 10, 1))

        assert [r.id for r in result.releases] == [1]
        assert result.complete is True

    def test_a_release_without_date_added_is_skipped(self, no_retry_client, respx_mock):
        api = _Discogs(respx_mock, [[(1, _added(2)), (2, None), (3, _added(1))]])

        result = releases_added_since(no_retry_client, CUTOFF)

        assert [r.id for r in result.releases] == [1, 3]
        assert result.complete is True
        assert api.looked_up() == [1, 2, 3]

    def test_a_release_repeated_across_pages_is_returned_once(
        self, no_retry_client, respx_mock
    ):
        api = _Discogs(
            respx_mock,
            [[(1, _added(3)), (2, _added(2))], [(2, _added(2)), (3, _added(1))]],
        )

        result = releases_added_since(no_retry_client, CUTOFF)

        assert [r.id for r in result.releases] == [1, 2, 3]
        assert api.looked_up() == [1, 2, 3]

    def test_no_results_is_empty_and_complete_after_one_request(
        self, no_retry_client, respx_mock, events
    ):
        _Discogs(respx_mock, [[]])

        result = releases_added_since(no_retry_client, CUTOFF)

        assert result.releases == []
        assert result.complete is True
        assert _sends(events) == 1


class TestCap:
    def test_a_cap_reached_mid_window_returns_what_was_found(
        self, no_retry_client, respx_mock, events
    ):
        api = _Discogs(respx_mock, TWO_PAGES)

        result = releases_added_since(no_retry_client, CUTOFF, max_requests=4)

        assert [r.id for r in result.releases] == [1, 2, 3]
        assert result.complete is False
        assert _sends(events) == 4
        assert api.search.call_count == 1

    def test_retries_count_and_may_overshoot_by_max_retries(self, respx_mock, events):
        client = Discogs(token="test-token", max_retries=3, on_request=events.append)
        _Discogs(respx_mock, TWO_PAGES, failures={2: 1})

        with patch("time.sleep"):
            result = releases_added_since(client, CUTOFF, max_requests=3)

        lookup_2 = next(e for e in events if e.url.endswith("/releases/2"))
        assert lookup_2.attempts == 2
        # The cap is reached during the lookup of release 2, which still completes.
        assert [r.id for r in result.releases] == [1, 2]
        assert result.complete is False
        assert 3 <= _sends(events) <= 3 + client.max_retries

    def test_cache_hits_cost_nothing(self, respx_mock):
        events: list[RequestEvent] = []
        client = Discogs(
            token="test-token", max_retries=0, cache=True, on_request=events.append
        )
        _Discogs(respx_mock, TWO_PAGES)
        first = releases_added_since(client, CUTOFF)
        events.clear()

        again = releases_added_since(client, CUTOFF, max_requests=1)

        assert again == first
        assert again.complete is True
        assert _sends(events) == 0
        client.close()


class TestSortCheck:
    def test_relevance_order_raises(self, no_retry_client, respx_mock):
        _Discogs(respx_mock, [[(1, _added(2)), (2, _added(3)), (3, _added(1))]])

        with pytest.raises(DiscogsError, match="date_added.*undocumented"):
            releases_added_since(no_retry_client, CUTOFF)

    def test_an_unsampled_inversion_goes_unnoticed(self, no_retry_client, respx_mock):
        # Release 3 is newer than the cutoff but sorted after release 2, which is
        # older: the scan stops at release 2 and never sees it. This pins the
        # documented limitation, not a desired outcome.
        api = _Discogs(respx_mock, [[(1, _added(2)), (2, _added(-1)), (3, _added(1))]])

        result = releases_added_since(no_retry_client, CUTOFF)

        assert [r.id for r in result.releases] == [1]
        assert result.complete is True
        assert api.looked_up() == [1, 2]


class TestArguments:
    @pytest.mark.parametrize(
        "params",
        [{"type": "artist"}, {"sort": "year"}, {"sort_order": "asc"}, {"page": 2}],
    )
    def test_owned_search_params_raise_before_any_request(
        self, no_retry_client, respx_mock, params
    ):
        with pytest.raises(ValueError, match=next(iter(params))):
            releases_added_since(no_retry_client, CUTOFF, **params)

        assert not respx_mock.calls

    def test_type_release_is_accepted(self, no_retry_client, respx_mock):
        _Discogs(respx_mock, [[]])

        result = releases_added_since(no_retry_client, CUTOFF, type="release")

        assert result.complete is True

    @pytest.mark.parametrize(
        ("since", "max_requests", "error"),
        [
            (datetime(2026, 10, 1), None, ValueError),  # noqa: DTZ001 - naive on purpose
            ("2026-10-01", None, TypeError),
            (CUTOFF, 0, ValueError),
        ],
    )
    def test_invalid_arguments_raise_before_any_request(
        self, no_retry_client, respx_mock, since, max_requests, error
    ):
        with pytest.raises(error):
            releases_added_since(no_retry_client, since, max_requests=max_requests)

        assert not respx_mock.calls
