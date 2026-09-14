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


# KLUDGE: sleep-based polling. A wantlist write is not visible to the next read
# for tens of seconds, and the API exposes nothing to wait on, so the only lever
# is retrying. Measured on 2026-09-13: a `PUT /users/{u}/wants/{id}` that
# returned 201 was still missing from `GET /users/{u}/wants` after 17s and
# present after 37s. Remove this if Discogs ever makes the write read-your-own.
def eventually(
    predicate: Callable[[], bool], *, attempts: int = 6, delay: float = 10.0
) -> bool:
    """Poll ``predicate`` until it holds, to absorb the observed write lag.

    Defaults cover a 50s window, comfortably past the worst lag measured so far.
    Each attempt costs one API call, so keep ``attempts`` small: the suite shares
    a 60/min budget.
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

# ── Tags for everything this suite creates ───────────────────────────────
#
# Nothing here resets the account: a folder or want the suite creates is removed
# by the test that created it. A run killed mid-test (cancelled job, timeout,
# dropped connection) skips that cleanup, so every write is tagged and the next
# run reclaims what it recognises as its own. That is the whole of the reset
# story, and it only works for tagged objects.

TEST_FOLDER_PREFIX = "discogs-sdk integration"
WANT_MARKER = "added by the discogs-sdk integration suite"


def delete_test_folders(client, username: str) -> None:
    """Delete every collection folder this suite owns, emptying it first.

    Only folders whose name carries ``TEST_FOLDER_PREFIX`` are touched, and only
    this suite creates those, so the instances inside one are its own. Discogs
    refuses to delete a non-empty folder, hence the two steps.

    Each listing is materialised before anything is deleted: the paginator
    fetches pages as it is consumed, and removing items mid-iteration shifts the
    page boundaries under it.
    """
    collection = client.users.get(username).collection
    folders = [
        folder
        for folder in collection.folders.list()
        if folder.name.startswith(TEST_FOLDER_PREFIX)
    ]
    for folder in folders:
        releases = collection.folders.get(folder.id).releases
        items = list(releases.list())
        for item in items:
            assert item.instance_id is not None, (
                f"release {item.id} in folder {folder.id} has no instance_id, "
                "so the copy to delete cannot be identified"
            )
            releases.get(item.id).instances.delete(item.instance_id)
        collection.folders.delete(folder.id)


def unavailable(reason: str) -> None:
    """Skip locally, fail on GitHub Actions.

    A leftover this suite cannot claim means the test stops running. Locally
    that is the right answer — the account may be the developer's own, and its
    data is not ours to touch. In the scheduled job it is a silent hole in the
    one thing that watches for API change, so it has to be loud there.

    ``GITHUB_ACTIONS`` rather than ``CI``: editors and terminals set ``CI``
    (this repo's own dev shell does), which would turn every local skip into a
    failure.
    """
    if os.environ.get("GITHUB_ACTIONS"):
        pytest.fail(reason)
    pytest.skip(reason)


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


@pytest.fixture(scope="session")
def scratch_folder(client, username):
    """A collection folder owned by this suite, empty at both ends of the run.

    Writes go here rather than into folder 1 (Uncategorized): that folder holds
    the account's real copies, and a leftover instance there is
    indistinguishable from one the owner added. Anything a previous run left is
    swept before the fresh folder is created, so a killed run costs nothing.
    """
    delete_test_folders(client, username)
    folder = client.users.get(username).collection.folders.create(
        name=f"{TEST_FOLDER_PREFIX} scratch"
    )
    yield folder
    delete_test_folders(client, username)
