"""Tests for exception hierarchy."""

from __future__ import annotations

from discogs_sdk._exceptions import (
    AuthenticationError,
    DiscogsAPIError,
    DiscogsConnectionError,
    DiscogsError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)


class TestHierarchy:
    def test_discogs_error_is_base(self):
        assert issubclass(DiscogsAPIError, DiscogsError)

    def test_connection_error_is_discogs_error(self):
        assert issubclass(DiscogsConnectionError, DiscogsError)

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
        err = RateLimitError("limited", status_code=429, response_body={}, retry_after="30")
        assert err.retry_after == "30"

    def test_inherits_api_error_fields(self):
        err = RateLimitError("limited", status_code=429, response_body={"message": "slow down"}, retry_after="5")
        assert err.status_code == 429
        assert err.response_body == {"message": "slow down"}
        assert str(err) == "429: limited"


class TestValidationError:
    def test_inherits_api_error_fields(self):
        err = ValidationError("invalid", status_code=422, response_body={"message": "invalid"})
        assert err.status_code == 422
        assert str(err) == "422: invalid"
