# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

"""OAuth 1.0a helpers for the Discogs API (PLAINTEXT signature method).

Failures raise the SDK's exceptions: HTTP errors map like the client's
(``AuthenticationError``, ``ForbiddenError``, ``RateLimitError``,
``DiscogsAPIError``), transport errors raise ``DiscogsConnectionError``, and a
successful response missing ``oauth_token`` or ``oauth_token_secret`` raises
``DiscogsAPIError``. Neither helper retries: the access-token exchange is not an
idempotent read.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode

import httpx2

from discogs_sdk._base_client import (
    DEFAULT_BASE_URL,
    USER_AGENT,
    build_oauth_header,
    error_message,
    raise_for_response,
)
from discogs_sdk._exceptions import DiscogsAPIError, DiscogsConnectionError
from discogs_sdk._oauth_types import AccessToken, RequestToken

_ACCESS_TOKEN_PATH = "/oauth/access_token"
_AUTHORIZE_URL = "https://www.discogs.com/oauth/authorize"
_REQUEST_TOKEN_PATH = "/oauth/request_token"


def _send(method: str, url: str, auth_header: str) -> httpx2.Response:
    """Send one OAuth request and raise the SDK exception for any failure."""
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": auth_header,
        "User-Agent": USER_AGENT,
    }
    try:
        with httpx2.Client() as client:
            response = client.request(method, url, headers=headers)
    except httpx2.RequestError as exc:
        raise DiscogsConnectionError(str(exc)) from exc
    raise_for_response(response)
    return response


def _parse_token(response: httpx2.Response) -> tuple[str, str]:
    """Return ``(oauth_token, oauth_token_secret)`` from a token response body."""
    parsed = parse_qs(response.text)
    token = parsed.get("oauth_token", [""])[0]
    token_secret = parsed.get("oauth_token_secret", [""])[0]
    if token and token_secret:
        return (token, token_secret)
    message = "OAuth response lacks oauth_token or oauth_token_secret"
    if problem := parsed.get("oauth_problem"):
        message = f"{message} (oauth_problem={problem[0]})"
    raise DiscogsAPIError(
        error_message(message),
        status_code=response.status_code,
        response_body=response.text,
    )


def get_request_token(
    consumer_key: str,
    consumer_secret: str,
    callback_url: str = "oob",
    *,
    base_url: str = DEFAULT_BASE_URL,
) -> RequestToken:
    """Step 1-2 of the OAuth flow: obtain a request token and authorize URL.

    Returns a RequestToken with the token, secret, and a URL to redirect
    the user to for authorization.

    Raises:
        DiscogsAPIError: The request was rejected (an ``AuthenticationError``,
            ``ForbiddenError`` or ``RateLimitError`` where the status says so),
            or the response lacked the token fields.
        DiscogsConnectionError: No response was received.
    """
    auth_header = build_oauth_header(
        callback=callback_url,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
    )
    response = _send("GET", f"{base_url.rstrip('/')}{_REQUEST_TOKEN_PATH}", auth_header)
    token, token_secret = _parse_token(response)
    return RequestToken(
        authorize_url=f"{_AUTHORIZE_URL}?{urlencode({'oauth_token': token})}",
        oauth_token_secret=token_secret,
        oauth_token=token,
    )


def get_access_token(
    consumer_key: str,
    consumer_secret: str,
    request_token: str,
    request_token_secret: str,
    verifier: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
) -> AccessToken:
    """Step 4 of the OAuth flow: exchange the request token for an access token.

    The verifier is obtained after the user authorizes the app at the
    authorize URL from get_request_token(). The exchange is sent once and never
    retried.

    Raises:
        DiscogsAPIError: The exchange was rejected (an ``AuthenticationError``,
            ``ForbiddenError`` or ``RateLimitError`` where the status says so),
            or the response lacked the token fields.
        DiscogsConnectionError: No response was received.
    """
    auth_header = build_oauth_header(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        token_secret=request_token_secret,
        token=request_token,
        verifier=verifier,
    )
    response = _send("POST", f"{base_url.rstrip('/')}{_ACCESS_TOKEN_PATH}", auth_header)
    token, token_secret = _parse_token(response)
    return AccessToken(oauth_token=token, oauth_token_secret=token_secret)
