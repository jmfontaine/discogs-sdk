"""Shared fixtures for integration tests.

These tests hit the real Discogs API. They require DISCOGS_TOKEN set in the
environment and are excluded from the default test run. Use ``just test-integration``
to run them explicitly.

Rate limits: authenticated requests are limited to 60/min. All fixtures are
session-scoped so we create a single client for the entire run. Keep total
API calls modest (<40) to stay well within the limit.
"""

import os

import pytest

from discogs_sdk import Discogs

# ── Well-known NIN-related Discogs IDs ───────────────────────────────────

ARTIST_ID = 3857  # Nine Inch Nails
MASTER_ID = 3719  # The Downward Spiral (master)
RELEASE_ID = 8851865  # The Downward Spiral (US CD, 1994)
LABEL_ID = 647  # Nothing Records
CRUD_RELEASE_ID = 9154868  # Pretty Hate Machine (for wantlist/collection CRUD)


@pytest.fixture(scope="session")
def token():
    tok = os.environ.get("DISCOGS_TOKEN")
    if not tok:
        pytest.skip("DISCOGS_TOKEN not set")
    return tok


@pytest.fixture(scope="session")
def client(token):
    with Discogs(token=token) as c:
        yield c


@pytest.fixture(scope="session")
def username(client):
    """Authenticated user's username, resolved once per session."""
    return client.user.identity().username
