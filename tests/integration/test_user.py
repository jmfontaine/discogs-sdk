"""Integration tests for user endpoints (read-only)."""

import pytest

from discogs_sdk.models.user import Identity

pytestmark = pytest.mark.integration


class TestIdentity:
    def test_identity_returns_authenticated_user(self, client):
        identity = client.user.identity()
        assert isinstance(identity, Identity)
        assert isinstance(identity.id, int)
        assert isinstance(identity.username, str)
        assert len(identity.username) > 0


class TestUserProfile:
    def test_get_user_profile(self, client, username):
        user = client.users.get(username)
        # Accessing a data attribute triggers lazy resolution
        assert user.username == username
        assert isinstance(user.id, int)
        assert isinstance(user.registered, str)
