"""Tests for BaseClient pure logic (no HTTP)."""

from __future__ import annotations

import pytest

from discogs_sdk._base_client import USER_AGENT, BaseClient, build_oauth_header
from discogs_sdk._exceptions import (
    AuthenticationError,
    DiscogsAPIError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)


class TestBuildUrl:
    def test_simple_path(self):
        c = BaseClient(token="t")
        assert c._build_url("/releases/1") == "https://api.discogs.com/releases/1"

    def test_strips_trailing_slash_from_base(self):
        c = BaseClient(token="t", base_url="https://api.discogs.com/")
        assert c._build_url("/releases/1") == "https://api.discogs.com/releases/1"

    def test_custom_base_url(self):
        c = BaseClient(token="t", base_url="https://custom.api.com")
        assert c._build_url("/foo") == "https://custom.api.com/foo"


class TestBuildHeaders:
    def test_includes_default_user_agent(self):
        c = BaseClient(token="t")
        headers = c._build_headers()
        assert headers["User-Agent"] == USER_AGENT

    def test_custom_user_agent(self):
        c = BaseClient(token="t", user_agent="MyApp/1.0")
        headers = c._build_headers()
        assert headers["User-Agent"] == "MyApp/1.0"

    def test_includes_auth_with_token(self):
        c = BaseClient(token="my-token")
        headers = c._build_headers()
        assert headers["Authorization"] == "Discogs token=my-token"

    def test_no_auth_without_token(self, monkeypatch):
        monkeypatch.delenv("DISCOGS_TOKEN", raising=False)
        c = BaseClient()
        headers = c._build_headers()
        assert "Authorization" not in headers

    def test_includes_accept_json(self):
        c = BaseClient(token="t")
        headers = c._build_headers()
        assert headers["Accept"] == "application/json"

    def test_key_secret_auth(self, monkeypatch):
        monkeypatch.delenv("DISCOGS_TOKEN", raising=False)
        c = BaseClient(consumer_key="mykey", consumer_secret="mysecret")
        headers = c._build_headers()
        assert headers["Authorization"] == "Discogs key=mykey, secret=mysecret"

    def test_token_takes_precedence_over_key_secret(self):
        c = BaseClient(token="t", consumer_key="k", consumer_secret="s")
        headers = c._build_headers()
        assert headers["Authorization"] == "Discogs token=t"

    def test_oauth_headers_not_in_build_headers(self, monkeypatch):
        monkeypatch.delenv("DISCOGS_TOKEN", raising=False)
        c = BaseClient(
            consumer_key="k",
            consumer_secret="s",
            access_token="at",
            access_token_secret="ats",
        )
        headers = c._build_headers()
        # OAuth headers are per-request, not in build_headers
        assert "Authorization" not in headers

    def test_uses_oauth_property(self, monkeypatch):
        monkeypatch.delenv("DISCOGS_TOKEN", raising=False)
        c = BaseClient(
            consumer_key="k",
            consumer_secret="s",
            access_token="at",
            access_token_secret="ats",
        )
        assert c._uses_oauth is True

    def test_uses_oauth_false_for_token(self):
        c = BaseClient(token="t")
        assert c._uses_oauth is False

    def test_uses_oauth_false_for_key_secret_only(self, monkeypatch):
        monkeypatch.delenv("DISCOGS_TOKEN", raising=False)
        c = BaseClient(consumer_key="k", consumer_secret="s")
        assert c._uses_oauth is False


class TestTokenResolution:
    def test_explicit_token(self):
        c = BaseClient(token="explicit")
        assert c._token == "explicit"

    def test_env_var_fallback(self, monkeypatch):
        monkeypatch.setenv("DISCOGS_TOKEN", "from-env")
        c = BaseClient()
        assert c._token == "from-env"

    def test_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv("DISCOGS_TOKEN", "from-env")
        c = BaseClient(token="explicit")
        assert c._token == "explicit"

    def test_no_token(self, monkeypatch):
        monkeypatch.delenv("DISCOGS_TOKEN", raising=False)
        c = BaseClient()
        assert c._token is None

    def test_consumer_key_from_env(self, monkeypatch):
        monkeypatch.setenv("DISCOGS_CONSUMER_KEY", "env-key")
        monkeypatch.setenv("DISCOGS_CONSUMER_SECRET", "env-secret")
        c = BaseClient()
        assert c._consumer_key == "env-key"
        assert c._consumer_secret == "env-secret"

    def test_access_token_from_env(self, monkeypatch):
        monkeypatch.setenv("DISCOGS_ACCESS_TOKEN", "env-at")
        monkeypatch.setenv("DISCOGS_ACCESS_TOKEN_SECRET", "env-ats")
        c = BaseClient()
        assert c._access_token == "env-at"
        assert c._access_token_secret == "env-ats"

    def test_explicit_overrides_env_for_consumer(self, monkeypatch):
        monkeypatch.setenv("DISCOGS_CONSUMER_KEY", "env-key")
        c = BaseClient(consumer_key="explicit-key")
        assert c._consumer_key == "explicit-key"


class TestBuildOAuthHeader:
    def test_contains_required_params(self):
        header = build_oauth_header(
            consumer_key="ck",
            consumer_secret="cs",
            token="tk",
            token_secret="ts",
        )
        assert header.startswith("OAuth ")
        assert 'oauth_consumer_key="ck"' in header
        assert "oauth_nonce=" in header
        assert 'oauth_signature_method="PLAINTEXT"' in header
        assert "oauth_timestamp=" in header
        assert 'oauth_token="tk"' in header
        assert 'oauth_signature="cs%26ts"' in header

    def test_omits_token_when_empty(self):
        header = build_oauth_header(consumer_key="ck", consumer_secret="cs")
        assert "oauth_token" not in header

    def test_includes_verifier(self):
        header = build_oauth_header(
            consumer_key="ck",
            consumer_secret="cs",
            verifier="v123",
        )
        assert 'oauth_verifier="v123"' in header

    def test_includes_callback(self):
        header = build_oauth_header(
            consumer_key="ck",
            consumer_secret="cs",
            callback="https://example.com/cb",
        )
        assert "oauth_callback=" in header


class TestMaybeRaise:
    def test_2xx_passes(self):
        c = BaseClient(token="t")
        c._maybe_raise(200, {"ok": True})  # should not raise

    def test_401_raises_authentication_error(self):
        c = BaseClient(token="t")
        with pytest.raises(AuthenticationError) as exc_info:
            c._maybe_raise(401, {"message": "Unauthorized"})
        assert exc_info.value.status_code == 401
        assert "Unauthorized" in str(exc_info.value)

    def test_403_raises_forbidden_error(self):
        c = BaseClient(token="t")
        with pytest.raises(ForbiddenError) as exc_info:
            c._maybe_raise(403, {"message": "Forbidden"})
        assert exc_info.value.status_code == 403
        assert "Forbidden" in str(exc_info.value)

    def test_404_raises_not_found(self):
        c = BaseClient(token="t")
        with pytest.raises(NotFoundError) as exc_info:
            c._maybe_raise(404, {"message": "Not Found"})
        assert exc_info.value.status_code == 404

    def test_422_raises_validation_error(self):
        c = BaseClient(token="t")
        with pytest.raises(ValidationError) as exc_info:
            c._maybe_raise(422, {"message": "Invalid rating"})
        assert exc_info.value.status_code == 422

    def test_429_raises_rate_limit(self):
        c = BaseClient(token="t")
        with pytest.raises(RateLimitError) as exc_info:
            c._maybe_raise(429, {"message": "Rate limited"})
        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after is None

    def test_429_with_retry_after(self):
        c = BaseClient(token="t")
        with pytest.raises(RateLimitError) as exc_info:
            c._maybe_raise(429, {"message": "Rate limited"}, retry_after="30")
        assert exc_info.value.retry_after == "30"

    def test_500_raises_generic_api_error(self):
        c = BaseClient(token="t")
        with pytest.raises(DiscogsAPIError) as exc_info:
            c._maybe_raise(500, {"message": "Internal Server Error"})
        assert exc_info.value.status_code == 500

    def test_dict_body_extracts_message(self):
        c = BaseClient(token="t")
        with pytest.raises(DiscogsAPIError) as exc_info:
            c._maybe_raise(400, {"message": "Bad Request"})
        assert "Bad Request" in str(exc_info.value)

    def test_string_body_passed_through(self):
        c = BaseClient(token="t")
        with pytest.raises(DiscogsAPIError) as exc_info:
            c._maybe_raise(400, "raw error text")
        assert "raw error text" in str(exc_info.value)
        assert exc_info.value.response_body == "raw error text"

    def test_attributes_set(self):
        c = BaseClient(token="t")
        body = {"message": "test"}
        with pytest.raises(DiscogsAPIError) as exc_info:
            c._maybe_raise(418, body)
        assert exc_info.value.status_code == 418
        assert exc_info.value.response_body == body


class TestRetryDelay:
    def test_exponential_backoff(self):
        c = BaseClient(token="t")
        d0 = c._retry_delay(0)
        d1 = c._retry_delay(1)
        d2 = c._retry_delay(2)
        assert 1.0 <= d0 < 2.0  # 2^0 + random [0,1)
        assert 2.0 <= d1 < 3.0  # 2^1 + random [0,1)
        assert 4.0 <= d2 < 5.0  # 2^2 + random [0,1)

    def test_max_capped_at_60(self):
        c = BaseClient(token="t")
        d = c._retry_delay(10)  # 2^10 = 1024, but capped at 60
        assert 60.0 <= d < 61.0

    def test_retry_after_overrides(self):
        c = BaseClient(token="t")
        d = c._retry_delay(0, retry_after="42")
        assert d == 42.0

    def test_invalid_retry_after_falls_back(self):
        c = BaseClient(token="t")
        d = c._retry_delay(0, retry_after="not-a-number")
        assert 1.0 <= d < 2.0

    def test_max_retries_default(self):
        c = BaseClient(token="t")
        assert c.max_retries == 3

    def test_max_retries_custom(self):
        c = BaseClient(token="t", max_retries=5)
        assert c.max_retries == 5


class TestBuildOAuthHeaderForRequest:
    def test_returns_oauth_header(self, monkeypatch):
        monkeypatch.delenv("DISCOGS_TOKEN", raising=False)
        c = BaseClient(
            consumer_key="ck",
            consumer_secret="cs",
            access_token="at",
            access_token_secret="ats",
        )
        header = c._build_oauth_header_for_request()
        assert header.startswith("OAuth ")
        assert 'oauth_consumer_key="ck"' in header
        assert 'oauth_token="at"' in header

    def test_raises_without_consumer_key(self):
        c = BaseClient(token="t")
        with pytest.raises(ValueError, match="consumer_key and consumer_secret"):
            c._build_oauth_header_for_request()

    def test_raises_without_access_token(self):
        c = BaseClient(consumer_key="ck", consumer_secret="cs")
        with pytest.raises(ValueError, match="access_token and access_token_secret"):
            c._build_oauth_header_for_request()
