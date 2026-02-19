#!/usr/bin/env python3
"""Interactive script to verify the full OAuth 1.0a flow against the Discogs API.

Walks through every step of the flow and validates each response.
Run manually when you need to confirm OAuth works end-to-end:

    uv run python scripts/verify_oauth.py

Requires DISCOGS_CONSUMER_KEY and DISCOGS_CONSUMER_SECRET in the environment
(or in .env via direnv).

On success, prints the access token and secret so you can store them for
automated integration tests (DISCOGS_ACCESS_TOKEN, DISCOGS_ACCESS_TOKEN_SECRET).
"""

from __future__ import annotations

import os
import sys
import webbrowser

from discogs_sdk import Discogs
from discogs_sdk.oauth import RequestToken, get_access_token, get_request_token


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Error: {name} not set in environment.", file=sys.stderr)
        sys.exit(1)
    return value


def main() -> None:
    consumer_key = _require_env("DISCOGS_CONSUMER_KEY")
    consumer_secret = _require_env("DISCOGS_CONSUMER_SECRET")

    # ── Step 1: Request token ────────────────────────────────────────
    print("Step 1: Requesting OAuth request token...")
    request_token: RequestToken = get_request_token(consumer_key, consumer_secret)

    assert request_token.oauth_token, "Request token is empty"
    assert request_token.oauth_token_secret, "Request token secret is empty"
    assert request_token.authorize_url.startswith("https://"), "Invalid authorize URL"
    print(f"  Token:     {request_token.oauth_token}")
    print(f"  Authorize: {request_token.authorize_url}")
    print()

    # ── Step 2: User authorization ───────────────────────────────────
    print("Step 2: Opening browser for authorization...")
    print(f"  If it doesn't open, visit: {request_token.authorize_url}")
    webbrowser.open(request_token.authorize_url)
    print()

    verifier = input("Step 3: Paste the verification code here: ").strip()
    if not verifier:
        print("Error: empty verifier.", file=sys.stderr)
        sys.exit(1)
    print()

    # ── Step 4: Access token ─────────────────────────────────────────
    print("Step 4: Exchanging for access token...")
    access = get_access_token(
        consumer_key,
        consumer_secret,
        request_token.oauth_token,
        request_token.oauth_token_secret,
        verifier,
    )

    assert access.oauth_token, "Access token is empty"
    assert access.oauth_token_secret, "Access token secret is empty"
    print(f"  Access token:  {access.oauth_token}")
    print(f"  Token secret:  {access.oauth_token_secret}")
    print()

    # ── Step 5: Verify authenticated request ─────────────────────────
    print("Step 5: Verifying OAuth client works...")
    with Discogs(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access.oauth_token,
        access_token_secret=access.oauth_token_secret,
    ) as client:
        identity = client.user.identity()

    assert identity.username, "Identity username is empty"
    print(f"  Authenticated as: {identity.username} (id={identity.id})")
    print()

    # ── Done ─────────────────────────────────────────────────────────
    print("OAuth flow verified successfully.")
    print()
    print("To use these tokens for integration tests, add to .env:")
    print(f"  DISCOGS_CONSUMER_KEY={consumer_key}")
    print(f"  DISCOGS_CONSUMER_SECRET={consumer_secret}")
    print(f"  DISCOGS_ACCESS_TOKEN={access.oauth_token}")
    print(f"  DISCOGS_ACCESS_TOKEN_SECRET={access.oauth_token_secret}")


if __name__ == "__main__":
    main()
