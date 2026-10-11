"""Tests for sync OAuth helpers."""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlsplit

import httpx2
import pytest
import respx

from discogs_sdk._exceptions import (
    AuthenticationError,
    DiscogsAPIError,
    DiscogsConnectionError,
    ForbiddenError,
    RateLimitError,
)
from discogs_sdk._sync._oauth import (
    AccessToken,
    RequestToken,
    get_access_token,
    get_request_token,
)

BASE_URL = "https://api.discogs.com"
REQUEST_TOKEN_PATH = "/oauth/request_token"
ACCESS_TOKEN_PATH = "/oauth/access_token"


def _request_token() -> RequestToken:
    return get_request_token("ck", "cs")


def _access_token() -> AccessToken:
    return get_access_token("ck", "cs", "req-token", "req-secret", "verifier")


# (HTTP method, path, call) for each helper, so failure handling is checked on both.
HELPERS = [
    pytest.param("GET", REQUEST_TOKEN_PATH, _request_token, id="request_token"),
    pytest.param("POST", ACCESS_TOKEN_PATH, _access_token, id="access_token"),
]


class TestGetRequestToken:
    def test_returns_request_token(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/oauth/request_token").mock(
                return_value=respx.MockResponse(
                    200, text="oauth_token=req-token&oauth_token_secret=req-secret"
                )
            )
            result = get_request_token("ck", "cs")
            assert isinstance(result, RequestToken)
            assert result.oauth_token == "req-token"
            assert result.oauth_token_secret == "req-secret"
            assert "oauth_token=req-token" in result.authorize_url

    def test_custom_callback_url(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/oauth/request_token").mock(
                return_value=respx.MockResponse(
                    200, text="oauth_token=t&oauth_token_secret=s"
                )
            )
            result = get_request_token(
                "ck", "cs", callback_url="https://example.com/cb"
            )
            assert result.oauth_token == "t"

    def test_401_raises_authentication_error(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get(REQUEST_TOKEN_PATH).mock(
                return_value=respx.MockResponse(
                    401, json={"message": "Invalid consumer."}
                )
            )
            with pytest.raises(AuthenticationError) as exc_info:
                get_request_token("ck", "cs")
        assert exc_info.value.status_code == 401
        assert exc_info.value.response_body == {"message": "Invalid consumer."}

    def test_400_raises_api_error_with_body(self):
        body = "oauth_problem=parameter_absent"
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get(REQUEST_TOKEN_PATH).mock(
                return_value=respx.MockResponse(400, text=body)
            )
            with pytest.raises(DiscogsAPIError) as exc_info:
                get_request_token("ck", "cs")
        assert type(exc_info.value) is DiscogsAPIError
        assert exc_info.value.status_code == 400
        assert exc_info.value.response_body == body

    @pytest.mark.parametrize("token", ["a&b", "a b", "a&b c=d"])
    def test_authorize_url_encodes_token(self, token):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get(REQUEST_TOKEN_PATH).mock(
                return_value=respx.MockResponse(
                    200,
                    text=urlencode({"oauth_token": token, "oauth_token_secret": "s"}),
                )
            )
            result = get_request_token("ck", "cs")
        assert result.oauth_token == token
        url = urlsplit(result.authorize_url)
        assert (url.scheme, url.netloc, url.path) == (
            "https",
            "www.discogs.com",
            "/oauth/authorize",
        )
        assert parse_qs(url.query, strict_parsing=True) == {"oauth_token": [token]}
        assert " " not in result.authorize_url


class TestGetAccessToken:
    def test_returns_access_token(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.post("/oauth/access_token").mock(
                return_value=respx.MockResponse(
                    200,
                    text="oauth_token=access-token&oauth_token_secret=access-secret",
                )
            )
            result = get_access_token(
                "ck", "cs", "req-token", "req-secret", "verifier-123"
            )
            assert isinstance(result, AccessToken)
            assert result.oauth_token == "access-token"
            assert result.oauth_token_secret == "access-secret"

    def test_403_raises_forbidden_error(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.post(ACCESS_TOKEN_PATH).mock(
                return_value=respx.MockResponse(403, json={"message": "Forbidden"})
            )
            with pytest.raises(ForbiddenError) as exc_info:
                _access_token()
        assert exc_info.value.status_code == 403

    def test_429_raises_rate_limit_error_with_retry_after(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.post(ACCESS_TOKEN_PATH).mock(
                return_value=respx.MockResponse(
                    429,
                    json={"message": "You are making requests too quickly."},
                    headers={"Retry-After": "5"},
                )
            )
            with pytest.raises(RateLimitError) as exc_info:
                _access_token()
        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after == "5"

    def test_500_is_sent_once(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.post(ACCESS_TOKEN_PATH).mock(
                return_value=respx.MockResponse(500, text="Internal Server Error")
            )
            with pytest.raises(DiscogsAPIError) as exc_info:
                _access_token()
        assert exc_info.value.status_code == 500
        assert route.call_count == 1

    def test_connection_error_is_sent_once(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            route = router.post(ACCESS_TOKEN_PATH).mock(
                side_effect=httpx2.ConnectError("refused")
            )
            with pytest.raises(DiscogsConnectionError):
                _access_token()
        assert route.call_count == 1


class TestTokenResponseFailures:
    @pytest.mark.parametrize(("method", "path", "call"), HELPERS)
    def test_oauth_problem_without_tokens(self, method, path, call):
        body = "oauth_problem=permission_denied"
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.route(method=method, path=path).mock(
                return_value=respx.MockResponse(200, text=body)
            )
            with pytest.raises(DiscogsAPIError) as exc_info:
                call()
        assert type(exc_info.value) is DiscogsAPIError
        assert exc_info.value.status_code == 200
        assert exc_info.value.response_body == body
        assert "permission_denied" in str(exc_info.value)

    @pytest.mark.parametrize(
        "body",
        [
            "",
            "oauth_token=t",
            "oauth_token_secret=s",
            "oauth_token=&oauth_token_secret=s",
        ],
    )
    @pytest.mark.parametrize(("method", "path", "call"), HELPERS)
    def test_missing_token_fields(self, method, path, call, body):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.route(method=method, path=path).mock(
                return_value=respx.MockResponse(200, text=body)
            )
            with pytest.raises(DiscogsAPIError) as exc_info:
                call()
        assert type(exc_info.value) is DiscogsAPIError
        assert exc_info.value.status_code == 200
        assert exc_info.value.response_body == body

    @pytest.mark.parametrize(
        "error",
        [httpx2.ConnectError("refused"), httpx2.ReadTimeout("timed out")],
        ids=["connect", "read_timeout"],
    )
    @pytest.mark.parametrize(("method", "path", "call"), HELPERS)
    def test_transport_error_raises_connection_error(self, method, path, call, error):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.route(method=method, path=path).mock(side_effect=error)
            with pytest.raises(DiscogsConnectionError) as exc_info:
                call()
        assert exc_info.value.__cause__ is error
