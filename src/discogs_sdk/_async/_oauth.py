"""OAuth 1.0a helpers for the Discogs API (PLAINTEXT signature method)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs

import httpx

from discogs_sdk._base_client import DEFAULT_BASE_URL, USER_AGENT, build_oauth_header

_ACCESS_TOKEN_PATH = "/oauth/access_token"
_AUTHORIZE_URL = "https://www.discogs.com/oauth/authorize"
_REQUEST_TOKEN_PATH = "/oauth/request_token"


@dataclass
class RequestToken:
    authorize_url: str
    oauth_token_secret: str
    oauth_token: str


@dataclass
class AccessToken:
    oauth_token: str
    oauth_token_secret: str


async def get_request_token(
    consumer_key: str,
    consumer_secret: str,
    callback_url: str = "oob",
    *,
    base_url: str = DEFAULT_BASE_URL,
) -> RequestToken:
    """Step 1-2 of the OAuth flow: obtain a request token and authorize URL.

    Returns a RequestToken with the token, secret, and a URL to redirect
    the user to for authorization.
    """
    auth_header = build_oauth_header(
        callback=callback_url,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
    )
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": auth_header,
        "User-Agent": USER_AGENT,
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url.rstrip('/')}{_REQUEST_TOKEN_PATH}", headers=headers)
    response.raise_for_status()

    parsed = parse_qs(response.text)
    token = parsed["oauth_token"][0]
    token_secret = parsed["oauth_token_secret"][0]
    return RequestToken(
        authorize_url=f"{_AUTHORIZE_URL}?oauth_token={token}",
        oauth_token_secret=token_secret,
        oauth_token=token,
    )


async def get_access_token(
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
    authorize URL from get_request_token().
    """
    auth_header = build_oauth_header(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        token_secret=request_token_secret,
        token=request_token,
        verifier=verifier,
    )
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": auth_header,
        "User-Agent": USER_AGENT,
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{base_url.rstrip('/')}{_ACCESS_TOKEN_PATH}", headers=headers)
    response.raise_for_status()

    parsed = parse_qs(response.text)
    return AccessToken(
        oauth_token=parsed["oauth_token"][0],
        oauth_token_secret=parsed["oauth_token_secret"][0],
    )
