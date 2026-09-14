"""Integration tests for wantlist CRUD.

Uses a single release and cleans up after itself. The want is tagged with
``WANT_MARKER`` so a run killed before its cleanup does not block the next one:
an entry carrying the tag is this suite's own debris and is reused, while an
untagged entry belongs to the account owner and is left alone. The one gap is a
run that dies between the create and the tagging update; that entry stays
untagged, and the next run skips this test rather than touch it.
"""

import pytest

from discogs_sdk.models.wantlist import Want
from tests.integration.conftest import (
    CRUD_RELEASE_ID,
    WANT_MARKER,
    eventually,
    unavailable,
)

pytestmark = pytest.mark.integration


class TestWantlistCRUD:
    """Create/list/delete cycle for a want this test owns."""

    def test_add_list_delete(self, client, username):
        wantlist = client.users.get(username).wantlist

        existing = next(
            (want for want in wantlist.list() if want.id == CRUD_RELEASE_ID), None
        )
        # A want the owner added carries their own notes and rating. Adding it
        # again would overwrite them, so leave it untouched. A tagged one is
        # debris from a killed run, and the create below simply overwrites it.
        if existing is not None and existing.notes != WANT_MARKER:
            unavailable(
                f"Release {CRUD_RELEASE_ID} is in the wantlist without this suite's "
                "tag, so it belongs to the account owner; refusing to modify it"
            )

        want = wantlist.create(release_id=CRUD_RELEASE_ID)

        try:
            # `notes` on the create (PUT) is accepted and dropped by Discogs;
            # only the update (POST) stores it, so the tag needs its own call.
            tagged = wantlist.update(CRUD_RELEASE_ID, notes=WANT_MARKER)
            assert isinstance(want, Want)
            assert want.id == CRUD_RELEASE_ID
            assert tagged.notes == WANT_MARKER
            # The write has been observed to lag behind the next read.
            assert eventually(
                lambda: CRUD_RELEASE_ID in [w.id for w in wantlist.list()]
            ), (
                f"Release {CRUD_RELEASE_ID} never showed up in the wantlist "
                "after being added"
            )
        finally:
            # Remove only the entry this test added.
            wantlist.delete(CRUD_RELEASE_ID)
