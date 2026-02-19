"""Integration tests for OAuth 1.0a authentication.

Requires pre-authorized OAuth tokens in the environment:
  DISCOGS_CONSUMER_KEY, DISCOGS_CONSUMER_SECRET,
  DISCOGS_ACCESS_TOKEN, DISCOGS_ACCESS_TOKEN_SECRET

Generate these tokens by running: uv run python scripts/verify_oauth.py
"""

import os

import pytest

from discogs_sdk import Discogs
from discogs_sdk.models.user import Identity

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def oauth_client():
    consumer_key = os.environ.get("DISCOGS_CONSUMER_KEY")
    consumer_secret = os.environ.get("DISCOGS_CONSUMER_SECRET")
    access_token = os.environ.get("DISCOGS_ACCESS_TOKEN")
    access_token_secret = os.environ.get("DISCOGS_ACCESS_TOKEN_SECRET")

    if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
        pytest.skip("OAuth credentials not set (DISCOGS_CONSUMER_KEY, etc.)")

    with Discogs(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
    ) as c:
        yield c


class TestOAuthClient:
    def test_identity(self, oauth_client):
        """OAuth-signed request returns the authenticated user."""
        identity = oauth_client.user.identity()
        assert isinstance(identity, Identity)
        assert isinstance(identity.username, str)
        assert len(identity.username) > 0

    def test_read_release(self, oauth_client):
        """OAuth credentials work for standard read endpoints."""
        release = oauth_client.releases.get(8851865)  # NIN - The Downward Spiral
        assert release.id == 8851865
        assert release.title == "The Downward Spiral"
