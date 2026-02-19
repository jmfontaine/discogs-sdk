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
    """Add release to folder 1 (Uncategorized), verify, then remove."""

    def test_add_and_remove_release(self, client, username):
        user = client.users.get(username)
        folder_releases = user.collection.folders.get(1).releases

        # Add release to Uncategorized (folder 1)
        folder_releases.create(release_id=CRUD_RELEASE_ID)

        try:
            # Verify it appears
            page = folder_releases.list()
            items = list(page)
            matching = [i for i in items if i.basic_information and i.basic_information.id == CRUD_RELEASE_ID]
            assert len(matching) > 0
            assert isinstance(matching[0], CollectionItem)

            instance_id = matching[0].instance_id
        finally:
            # Remove via instance delete (folder 1)
            user.collection.folders.get(1).releases.get(CRUD_RELEASE_ID).instances.delete(instance_id)


class TestCollectionFields:
    """Read-only: list custom fields."""

    def test_list_fields(self, client, username):
        fields = client.users.get(username).collection.fields.list()
        assert isinstance(fields, list)
        # Every collection has at least the built-in "Notes" field
        assert len(fields) > 0
