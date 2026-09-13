"""Integration tests for wantlist CRUD.

Uses a single release and cleans up after itself.
"""

import pytest

from discogs_sdk.models.wantlist import Want
from tests.integration.conftest import CRUD_RELEASE_ID, eventually

pytestmark = pytest.mark.integration


class TestWantlistCRUD:
    """Create/list/delete cycle for a want this test owns."""

    def test_add_list_delete(self, client, username):
        wantlist = client.users.get(username).wantlist

        # A want already on the account carries the user's own notes and rating.
        # Adding it again would overwrite them, so leave it untouched.
        if any(want.id == CRUD_RELEASE_ID for want in wantlist.list()):
            pytest.skip(f"Release {CRUD_RELEASE_ID} is already in the wantlist; refusing to modify it")

        want = wantlist.create(release_id=CRUD_RELEASE_ID)

        try:
            assert isinstance(want, Want)
            assert want.id == CRUD_RELEASE_ID
            # The write has been observed to lag behind the next read.
            assert eventually(lambda: CRUD_RELEASE_ID in [w.id for w in wantlist.list()]), (
                f"Release {CRUD_RELEASE_ID} never showed up in the wantlist after being added"
            )
        finally:
            # Remove only the entry this test added.
            wantlist.delete(CRUD_RELEASE_ID)
