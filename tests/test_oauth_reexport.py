"""The public OAuth helpers must return the same classes in both variants."""

from __future__ import annotations

import respx

from discogs_sdk.oauth import (
    AccessToken,
    RequestToken,
    async_get_access_token,
    async_get_request_token,
    get_access_token,
    get_request_token,
)
from tests.conftest import BASE_URL

REQUEST_TOKEN_BODY = (
    "oauth_token=req-token&oauth_token_secret=req-secret&oauth_callback_confirmed=true"
)
ACCESS_TOKEN_BODY = "oauth_token=acc-token&oauth_token_secret=acc-secret"


def test_reexport_symbols():
    assert callable(get_request_token)
    assert callable(get_access_token)
    assert callable(async_get_request_token)
    assert callable(async_get_access_token)


class TestSharedResultClasses:
    def test_sync_helpers_return_public_classes(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/oauth/request_token").respond(200, text=REQUEST_TOKEN_BODY)
            router.post("/oauth/access_token").respond(200, text=ACCESS_TOKEN_BODY)

            request_token = get_request_token("ck", "cs")
            access_token = get_access_token(
                "ck", "cs", "req-token", "req-secret", "123456"
            )

        assert isinstance(request_token, RequestToken)
        assert isinstance(access_token, AccessToken)
        assert request_token.oauth_token == "req-token"
        assert access_token.oauth_token == "acc-token"

    async def test_async_helpers_return_the_same_classes(self):
        with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
            router.get("/oauth/request_token").respond(200, text=REQUEST_TOKEN_BODY)
            router.post("/oauth/access_token").respond(200, text=ACCESS_TOKEN_BODY)

            request_token = await async_get_request_token("ck", "cs")
            access_token = await async_get_access_token(
                "ck", "cs", "req-token", "req-secret", "123456"
            )

        assert isinstance(request_token, RequestToken)
        assert isinstance(access_token, AccessToken)
        assert request_token.authorize_url.endswith("oauth_token=req-token")
        assert access_token.oauth_token_secret == "acc-secret"
