"""Tests for exception hierarchy."""

from __future__ import annotations

import copy
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from typing import Any, ClassVar

import pytest

from discogs_sdk._events import RateLimit
from discogs_sdk._exceptions import (
    AuthenticationError,
    CacheMissError,
    DiscogsAPIError,
    DiscogsConnectionError,
    DiscogsError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)

CACHE_URL = "https://api.discogs.com/releases/352665"


def _pickle_round_trip(exc: BaseException) -> Any:
    return pickle.loads(pickle.dumps(exc))


ROUND_TRIPS = pytest.mark.parametrize(
    "round_trip",
    [_pickle_round_trip, copy.copy, copy.deepcopy],
    ids=["pickle", "copy", "deepcopy"],
)


class _RecordingNotFoundError(NotFoundError):
    """Records every constructor call, to prove what reconstruction passes in."""

    calls: ClassVar[list[tuple[tuple[Any, ...], dict[str, Any]]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        type(self).calls.append((args, kwargs))
        super().__init__(*args, **kwargs)


def _raise_not_found() -> None:
    raise NotFoundError(
        "Release not found.",
        status_code=404,
        response_body={"message": "Release not found."},
    )


def _add_note_and_attribute(exc: BaseException) -> None:
    """Give ``exc`` a note and a caller-added ``extra`` attribute."""
    if sys.version_info >= (3, 11):
        exc.add_note("n")
    else:  # add_note() is 3.11+; it only appends to __notes__
        vars(exc)["__notes__"] = ["n"]
    vars(exc)["extra"] = 1  # an attribute no SDK class declares


class TestHierarchy:
    def test_discogs_error_is_base(self):
        assert issubclass(DiscogsAPIError, DiscogsError)

    def test_connection_error_is_discogs_error(self):
        assert issubclass(DiscogsConnectionError, DiscogsError)

    def test_cache_miss_error_is_discogs_error(self):
        assert issubclass(CacheMissError, DiscogsError)
        assert not issubclass(CacheMissError, DiscogsAPIError)

    def test_authentication_error(self):
        assert issubclass(AuthenticationError, DiscogsAPIError)

    def test_not_found_error(self):
        assert issubclass(NotFoundError, DiscogsAPIError)

    def test_rate_limit_error(self):
        assert issubclass(RateLimitError, DiscogsAPIError)

    def test_validation_error(self):
        assert issubclass(ValidationError, DiscogsAPIError)


class TestDiscogsAPIError:
    def test_str_format(self):
        err = DiscogsAPIError("msg", status_code=404, response_body={})
        assert str(err) == "404: msg"

    def test_attributes(self):
        body = {"message": "not found"}
        err = DiscogsAPIError("not found", status_code=404, response_body=body)
        assert err.status_code == 404
        assert err.response_body == body


class TestRateLimitError:
    def test_retry_after_default_none(self):
        err = RateLimitError("limited", status_code=429, response_body={})
        assert err.retry_after is None

    def test_retry_after_set(self):
        err = RateLimitError(
            "limited", status_code=429, response_body={}, retry_after="30"
        )
        assert err.retry_after == "30"

    def test_ratelimit_default_none(self):
        err = RateLimitError("limited", status_code=429, response_body={})
        assert err.ratelimit is None

    def test_ratelimit_set(self):
        err = RateLimitError(
            "limited",
            status_code=429,
            response_body={},
            ratelimit=RateLimit(60, 60, 0),
        )
        assert err.ratelimit == RateLimit(60, 60, 0)

    def test_inherits_api_error_fields(self):
        err = RateLimitError(
            "limited",
            status_code=429,
            response_body={"message": "slow down"},
            retry_after="5",
        )
        assert err.status_code == 429
        assert err.response_body == {"message": "slow down"}
        assert str(err) == "429: limited"


class TestValidationError:
    def test_inherits_api_error_fields(self):
        err = ValidationError(
            "invalid", status_code=422, response_body={"message": "invalid"}
        )
        assert err.status_code == 422
        assert str(err) == "422: invalid"


class TestCacheMissError:
    def test_message_and_attributes(self):
        err = CacheMissError("GET", "https://api.discogs.com/releases/352665")
        assert err.method == "GET"
        assert err.url == "https://api.discogs.com/releases/352665"
        assert str(err) == "Not cached: GET https://api.discogs.com/releases/352665"


class TestRateLimit:
    def test_from_headers_is_case_insensitive(self):
        headers = {
            "X-Discogs-Ratelimit": "60",
            "x-discogs-ratelimit-used": "14",
            "X-DISCOGS-RATELIMIT-REMAINING": "46",
        }
        assert RateLimit.from_headers(headers) == RateLimit(60, 14, 46)

    def test_from_headers_missing_header_is_none(self):
        headers = {"X-Discogs-Ratelimit": "60", "X-Discogs-Ratelimit-Used": "14"}
        assert RateLimit.from_headers(headers) is None

    def test_from_headers_non_integer_is_none(self):
        headers = {
            "X-Discogs-Ratelimit": "60",
            "X-Discogs-Ratelimit-Used": "fourteen",
            "X-Discogs-Ratelimit-Remaining": "46",
        }
        assert RateLimit.from_headers(headers) is None


class TestPickleAndCopy:
    @ROUND_TRIPS
    @pytest.mark.parametrize(
        ("cls", "status_code"),
        [
            (DiscogsAPIError, 500),
            (AuthenticationError, 401),
            (ForbiddenError, 403),
            (NotFoundError, 404),
            (ValidationError, 422),
        ],
    )
    @pytest.mark.parametrize(
        "body",
        [{"message": "Release not found."}, "<html>Bad Gateway</html>"],
        ids=["dict", "str"],
    )
    def test_api_errors(self, round_trip, cls, status_code, body):
        err = cls("Release not found.", status_code=status_code, response_body=body)
        clone = round_trip(err)
        assert type(clone) is cls
        assert clone is not err
        assert clone.args == ("Release not found.",)
        assert clone.status_code == status_code
        assert clone.response_body == body
        assert str(clone) == f"{status_code}: Release not found."

    @ROUND_TRIPS
    def test_rate_limit_error(self, round_trip):
        err = RateLimitError(
            "slow down",
            status_code=429,
            response_body={"message": "slow down"},
            retry_after="30",
            ratelimit=RateLimit(60, 60, 0),
        )
        clone = round_trip(err)
        assert type(clone) is RateLimitError
        assert clone.args == ("slow down",)
        assert clone.status_code == 429
        assert clone.response_body == {"message": "slow down"}
        assert clone.retry_after == "30"
        assert isinstance(clone.ratelimit, RateLimit)
        assert clone.ratelimit == RateLimit(60, 60, 0)
        assert str(clone) == "429: slow down"

    @ROUND_TRIPS
    def test_cache_miss_error(self, round_trip):
        clone = round_trip(CacheMissError("GET", CACHE_URL))
        assert type(clone) is CacheMissError
        assert clone.method == "GET"
        assert clone.url == CACHE_URL
        assert clone.args == (f"Not cached: GET {CACHE_URL}",)
        assert str(clone) == f"Not cached: GET {CACHE_URL}"

    @ROUND_TRIPS
    @pytest.mark.parametrize("cls", [DiscogsError, DiscogsConnectionError])
    def test_message_only_errors(self, round_trip, cls):
        clone = round_trip(cls("connection refused"))
        assert type(clone) is cls
        assert clone.args == ("connection refused",)
        assert str(clone) == "connection refused"

    @ROUND_TRIPS
    def test_notes_and_extra_attributes_restored(self, round_trip):
        err = RateLimitError("slow down", status_code=429, response_body={})
        _add_note_and_attribute(err)
        clone = round_trip(err)
        assert clone.__notes__ == ["n"]
        assert clone.extra == 1
        assert clone.status_code == 429

    @ROUND_TRIPS
    def test_constructor_receives_only_its_arguments(self, round_trip):
        err = _RecordingNotFoundError(
            "Release not found.", status_code=404, response_body={}
        )
        _add_note_and_attribute(err)
        _RecordingNotFoundError.calls.clear()
        clone = round_trip(err)
        assert _RecordingNotFoundError.calls == [
            (("Release not found.",), {"status_code": 404, "response_body": {}})
        ]
        assert type(clone) is _RecordingNotFoundError
        assert clone.__notes__ == ["n"]
        assert clone.extra == 1
        assert str(clone) == "404: Release not found."

    def test_raised_and_caught_error_pickles(self):
        with pytest.raises(NotFoundError) as info:
            _raise_not_found()
        clone = _pickle_round_trip(info.value)
        assert type(clone) is NotFoundError
        assert str(clone) == "404: Release not found."

    def test_error_crosses_process_boundary(self):
        with ProcessPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_raise_not_found)
            with pytest.raises(NotFoundError) as info:
                future.result()
        assert info.value.status_code == 404
        assert info.value.response_body == {"message": "Release not found."}
        assert str(info.value) == "404: Release not found."
