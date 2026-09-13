"""Integration tests for collection CRUD.

Creates a folder, adds a release, verifies, then cleans up.
"""

import pytest

from discogs_sdk.models.collection import CollectionFolder, CollectionItem
from tests.integration.conftest import CRUD_RELEASE_ID

pytestmark = pytest.mark.integration


class TestCollectionFolders:
    """Folder create/list/delete cycle."""

    def test_create_list_delete_folder(self, client, username):
        folder = client.users.get(username).collection.folders.create(name="SDK Test Folder")
        assert isinstance(folder, CollectionFolder)
        assert folder.name == "SDK Test Folder"

        try:
            # Verify it appears in the list
            folders = client.users.get(username).collection.folders.list()
            folder_ids = [f.id for f in folders]
            assert folder.id in folder_ids
        finally:
            client.users.get(username).collection.folders.delete(folder.id)


class TestCollectionReleases:
    """Add a release to folder 1 (Uncategorized), verify, then remove that copy."""

    def test_add_and_remove_release(self, client, username):
        user = client.users.get(username)
        folder_releases = user.collection.folders.get(1).releases

        # Keep the acknowledgement: the user may already own other copies of this
        # release, and only the instance created here may be removed.
        created = folder_releases.create(release_id=CRUD_RELEASE_ID)
        instance_id = created.instance_id

        try:
            items = list(folder_releases.list())
            mine = [item for item in items if item.instance_id == instance_id]
            assert len(mine) == 1
            assert isinstance(mine[0], CollectionItem)
            assert mine[0].basic_information is not None
            assert mine[0].basic_information.id == CRUD_RELEASE_ID
        finally:
            user.collection.folders.get(1).releases.get(CRUD_RELEASE_ID).instances.delete(instance_id)


class TestCollectionFields:
    """Read-only: list custom fields."""

    def test_list_fields(self, client, username):
        fields = client.users.get(username).collection.fields.list()
        assert isinstance(fields, list)
        # Every collection has at least the built-in "Notes" field
        assert len(fields) > 0
