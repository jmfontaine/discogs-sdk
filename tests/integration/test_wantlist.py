"""Integration tests for wantlist CRUD.

Uses a single release and cleans up after itself. The want is tagged with
``WANT_MARKER`` so a run killed before its cleanup does not block the next one:
an entry carrying the tag is this suite's own debris and is reused, while an
untagged entry belongs to the account owner and is left alone. The one gap is a
run that dies between the create and the tagging update; that entry stays
untagged, and the next run skips this test rather than touch it.

The wantlist has no read for a single want, so finding one means scanning the
listing. The test scans once before the create and once to confirm it, and
polls in between with one request per attempt: with ``n`` wants after the create
that is at most ``2 * ceil(n / 100) + 6`` reads (48 for 2,001 wants), plus the
create, the tagging update and the delete.
"""

import math

import pytest

from discogs_sdk.models.wantlist import Want
from tests.integration.conftest import (
    CRUD_RELEASE_ID,
    WANT_MARKER,
    eventually,
    unavailable,
)

pytestmark = pytest.mark.integration

# The largest page Discogs serves.
FULL_PAGE = 100
# Attempts eventually() makes before giving up.
ATTEMPTS = 6


class TestWantlistCRUD:
    """Create/list/delete cycle for a want this test owns."""

    def test_add_list_delete(self, client, username):
        wantlist = client.users.get(username).wantlist
        reads = 0  # wantlist GETs, counted from the pages each listing fetched

        scan = wantlist.list(per_page=FULL_PAGE)
        existing = next((want for want in scan if want.id == CRUD_RELEASE_ID), None)
        reads += scan.page or 1
        before = scan.total_items
        assert before is not None, "the wantlist listing carried no item count"
        # A want the owner added carries their own notes and rating. Adding it
        # again would overwrite them, so leave it untouched. A tagged one is
        # debris from a killed run, and the create below simply overwrites it.
        if existing is not None and existing.notes != WANT_MARKER:
            unavailable(
                f"Release {CRUD_RELEASE_ID} is in the wantlist without this suite's "
                "tag, so it belongs to the account owner; refusing to modify it"
            )
        # Overwriting the debris leaves the count where it was.
        expected = before if existing is not None else before + 1

        def visible() -> bool:
            # Assumes nobody else writes to this account while the suite runs, so
            # a count that reached `expected` means our want has landed.
            nonlocal reads
            # Page 1 of size 1 carries the total: a lagging write costs one
            # request per attempt instead of a rescan.
            probe = wantlist.list(per_page=1)
            next(probe, None)
            reads += 1
            if probe.total_items is None or probe.total_items < expected:
                return False
            confirm = wantlist.list(per_page=FULL_PAGE)
            found = any(want.id == CRUD_RELEASE_ID for want in confirm)
            reads += confirm.page or 1
            if not found:
                # Rescanning on every later attempt would blow the budget, so
                # stop here; the delete in `finally` still runs.
                pytest.fail(
                    f"The wantlist count reached {expected} but release "
                    f"{CRUD_RELEASE_ID} is not listed: either the count leads the "
                    "listing after a write, or something else wrote to the wantlist"
                )
            return True

        want = wantlist.create(release_id=CRUD_RELEASE_ID)

        try:
            # `notes` on the create (PUT) is accepted and dropped by Discogs;
            # only the update (POST) stores it, so the tag needs its own call.
            tagged = wantlist.update(CRUD_RELEASE_ID, notes=WANT_MARKER)
            assert isinstance(want, Want)
            assert want.id == CRUD_RELEASE_ID
            assert tagged.notes == WANT_MARKER
            # The write has been observed to lag behind the next read.
            assert eventually(visible, attempts=ATTEMPTS), (
                f"Release {CRUD_RELEASE_ID} never showed up in the wantlist "
                "after being added"
            )
            budget = 2 * math.ceil(expected / FULL_PAGE) + ATTEMPTS
            assert reads <= budget, (
                f"{reads} wantlist reads for {expected} wants, over the budget of "
                f"{budget}; did something else write to the wantlist mid-run?"
            )
        finally:
            # Remove only the entry this test added.
            wantlist.delete(CRUD_RELEASE_ID)
