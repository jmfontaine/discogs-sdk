"""Integration tests for collection CRUD.

Every folder created here carries ``TEST_FOLDER_PREFIX`` and every write lands
in this suite's own scratch folder, so a run that dies before its cleanup leaves
only tagged debris that the next run sweeps. Nothing touches folder 1
(Uncategorized), where the account's real copies live.
"""

import pytest

from discogs_sdk.models.collection import CollectionFolder, CollectionItem
from tests.integration.conftest import CRUD_RELEASE_ID, TEST_FOLDER_PREFIX, eventually

pytestmark = pytest.mark.integration


class TestCollectionFolders:
    """Folder create/list/delete cycle."""

    def test_create_list_delete_folder(self, client, username):
        folders = client.users.get(username).collection.folders
        name = f"{TEST_FOLDER_PREFIX} lifecycle"

        folder = folders.create(name=name)
        try:
            assert isinstance(folder, CollectionFolder)
            assert folder.name == name
            # Like every read-back of a write, the listing may lag behind it.
            assert eventually(lambda: folder.id in [f.id for f in folders.list()]), (
                f"Folder {folder.id} never showed up in the folder listing "
                "after being created"
            )
        finally:
            folders.delete(folder.id)


class TestCollectionReleases:
    """Add a release to the scratch folder, verify, then remove that copy."""

    def test_add_and_remove_release(self, client, username, scratch_folder):
        releases = (
            client.users.get(username)
            .collection.folders.get(scratch_folder.id)
            .releases
        )

        # Keep the acknowledgement: the account may hold other copies of this
        # release, and only the instance created here may be removed.
        created = releases.create(release_id=CRUD_RELEASE_ID)
        instance_id = created.instance_id

        try:
            # Scan only the scratch folder, and only for the instance created
            # here; keep what the last attempt found for the checks below.
            mine: list[CollectionItem] = []

            def instance_listed() -> bool:
                mine[:] = [
                    item for item in releases.list() if item.instance_id == instance_id
                ]
                return bool(mine)

            assert eventually(instance_listed), (
                f"Instance {instance_id} never showed up in folder "
                f"{scratch_folder.id} after being added"
            )
            assert len(mine) == 1
            assert isinstance(mine[0], CollectionItem)
            assert mine[0].basic_information is not None
            assert mine[0].basic_information.id == CRUD_RELEASE_ID
        finally:
            releases.get(CRUD_RELEASE_ID).instances.delete(instance_id)


class TestCollectionFields:
    """Read-only: list custom fields."""

    def test_list_fields(self, client, username):
        fields = client.users.get(username).collection.fields.list()
        assert isinstance(fields, list)
        # Every collection has at least the built-in "Notes" field
        assert len(fields) > 0
