"""Shared fixtures for integration tests.

These tests hit the real Discogs API. They require DISCOGS_TOKEN set in the
environment and are excluded from the default test run. Use ``just test-integration``
to run them explicitly.

Rate limits: authenticated requests are limited to 60/min. All fixtures are
session-scoped so we create a single client for the entire run. Keep total
API calls modest (<40) to stay well within the limit.
"""

import os
import time
from collections.abc import Callable

import pytest

from discogs_sdk import Discogs


# KLUDGE: sleep-based polling. A wantlist entry was seen missing from the read
# that followed a successful write, and the API exposes nothing to wait on, so
# the only lever is retrying. Remove this if the lag turns out to have been a
# transient Discogs fault rather than normal behaviour.
def eventually(predicate: Callable[[], bool], *, attempts: int = 4, delay: float = 1.0) -> bool:
    """Poll ``predicate`` until it holds, to tolerate observed read-after-write lag.

    A wantlist entry has been seen missing from the next read after a successful
    write, so one failed read is not proof that the write was lost. Each attempt
    costs one API call, so keep ``attempts`` small: the suite shares a 60/min
    budget.
    """
    for attempt in range(attempts):
        if predicate():
            return True
        if attempt < attempts - 1:
            time.sleep(delay)
    return False


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
