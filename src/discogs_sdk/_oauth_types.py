"""Result types for the OAuth 1.0a flow.

They live outside the generated variants so the sync and async helpers return
the very same classes, and so ``discogs_sdk.oauth`` can annotate both.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RequestToken:
    authorize_url: str
    oauth_token_secret: str
    oauth_token: str


@dataclass
class AccessToken:
    oauth_token: str
    oauth_token_secret: str
