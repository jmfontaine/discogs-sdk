"""Integration tests for wantlist CRUD.

Uses a single release and cleans up after itself.
"""

import pytest

from discogs_sdk.models.wantlist import Want

from tests.integration.conftest import CRUD_RELEASE_ID

pytestmark = pytest.mark.integration


class TestWantlistCRUD:
    """Full create/list/delete cycle for the wantlist."""

    def test_add_list_delete(self, client, username):
        wantlist = client.users.get(username).wantlist

        # Add to wantlist
        want = wantlist.create(release_id=CRUD_RELEASE_ID)
        assert isinstance(want, Want)
        assert want.id == CRUD_RELEASE_ID

        try:
            # Verify it appears in the list
            page = wantlist.list()
            ids = [w.id for w in page]
            assert CRUD_RELEASE_ID in ids
        finally:
            # Always clean up
            wantlist.delete(CRUD_RELEASE_ID)
