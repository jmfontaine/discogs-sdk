"""The live integration workflows must not touch pre-existing user data.

These run the integration test bodies, and the sweep they rely on, against HTTP
mocks, so the destructive paths are exercised without a real account.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import respx
from _pytest.outcomes import Failed, Skipped

from discogs_sdk import Discogs
from tests.conftest import (
    make_collection_folder,
    make_collection_instance_created,
    make_paginated_response,
    mock_router,
)
from tests.integration import conftest as integration_conftest
from tests.integration import test_collection as collection_workflow
from tests.integration import test_wantlist as wantlist_workflow
from tests.integration.conftest import (
    CRUD_RELEASE_ID,
    TEST_FOLDER_PREFIX,
    WANT_MARKER,
    delete_test_folders,
)

USERNAME = "trent_reznor"
SCRATCH_FOLDER_ID = 42
FOLDERS_PATH = f"/users/{USERNAME}/collection/folders"
FOLDER_PATH = f"{FOLDERS_PATH}/{SCRATCH_FOLDER_ID}/releases"
# Carries the prefix, but not at the start: a folder the owner named, not ours.
NEAR_MISS_FOLDER_ID = 8

EXISTING_INSTANCE = {
    "id": CRUD_RELEASE_ID,
    "instance_id": 10,
    "folder_id": SCRATCH_FOLDER_ID,
    "rating": 5,
    "notes": [{"field_id": 1, "value": "First pressing, keep"}],
    "basic_information": {"id": CRUD_RELEASE_ID, "title": "Pretty Hate Machine"},
}
CREATED_INSTANCE = {
    "id": CRUD_RELEASE_ID,
    "instance_id": 20,
    "folder_id": SCRATCH_FOLDER_ID,
    "basic_information": {"id": CRUD_RELEASE_ID, "title": "Pretty Hate Machine"},
}


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    """The delays ``eventually()`` asked for, none of them slept for real.

    Only the ``time`` name inside the integration conftest is replaced.
    Patching ``time.sleep`` by dotted path would replace it process-wide, the
    SDK's own retry sleeps included.
    """
    requested: list[float] = []
    monkeypatch.setattr(
        integration_conftest, "time", SimpleNamespace(sleep=requested.append)
    )
    return requested


def in_turn(*bodies):
    """A respx side effect serving each JSON body once, then the last for good.

    Stands in for a listing that lags behind a write and then catches up.
    """
    remaining = list(bodies)

    def respond(_request):
        body = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        return respx.MockResponse(200, json=body)

    return respond


@pytest.fixture
def client():
    with Discogs(token="test-token") as discogs:
        yield discogs


@pytest.fixture
def scratch_folder():
    """Stand-in for the session fixture the collection workflow receives."""
    return SimpleNamespace(id=SCRATCH_FOLDER_ID)


class TestFolderSweep:
    """The sweep that reclaims debris is the suite's one unattended deletion."""

    def test_deletes_only_folders_this_suite_owns(self, client):
        with mock_router(assert_all_called=False) as router:
            router.get(FOLDERS_PATH).respond(
                200,
                json={
                    "folders": [
                        make_collection_folder(id=0, name="All"),
                        make_collection_folder(id=1, name="Uncategorized"),
                        make_collection_folder(id=7, name="Vinyl"),
                        make_collection_folder(
                            id=NEAR_MISS_FOLDER_ID,
                            name="Old discogs-sdk integration stuff",
                        ),
                        make_collection_folder(
                            id=SCRATCH_FOLDER_ID, name=f"{TEST_FOLDER_PREFIX} scratch"
                        ),
                    ]
                },
            )
            scratch_listed = router.get(FOLDER_PATH).respond(
                200, json=make_paginated_response("releases", [])
            )
            router.delete(f"{FOLDERS_PATH}/{SCRATCH_FOLDER_ID}").respond(204)
            # Mocked so that touching the near miss fails the assertions below
            # rather than respx's unmatched-request guard.
            near_miss_listed = router.get(
                f"{FOLDERS_PATH}/{NEAR_MISS_FOLDER_ID}/releases"
            ).respond(200, json=make_paginated_response("releases", []))
            near_miss_deleted = router.delete(
                f"{FOLDERS_PATH}/{NEAR_MISS_FOLDER_ID}"
            ).respond(204)

            delete_test_folders(client, USERNAME)

            deleted = [
                call.request.url.path
                for call in router.calls
                if call.request.method == "DELETE"
            ]
            assert scratch_listed.called
            assert deleted == [f"{FOLDERS_PATH}/{SCRATCH_FOLDER_ID}"]
            assert near_miss_listed.call_count == 0
            assert near_miss_deleted.call_count == 0

    def test_empties_a_leftover_folder_before_deleting_it(self, client):
        with mock_router() as router:
            router.get(FOLDERS_PATH).respond(
                200,
                json={
                    "folders": [
                        make_collection_folder(
                            id=SCRATCH_FOLDER_ID, name=f"{TEST_FOLDER_PREFIX} scratch"
                        )
                    ]
                },
            )
            # The instance is gone once deleted, and the next read shows that.
            router.get(FOLDER_PATH).mock(
                side_effect=in_turn(
                    make_paginated_response("releases", [CREATED_INSTANCE]),
                    make_paginated_response("releases", []),
                )
            )
            router.delete(f"{FOLDER_PATH}/{CRUD_RELEASE_ID}/instances/20").respond(204)
            router.delete(f"{FOLDERS_PATH}/{SCRATCH_FOLDER_ID}").respond(204)

            delete_test_folders(client, USERNAME)

            deleted = [
                call.request.url.path
                for call in router.calls
                if call.request.method == "DELETE"
            ]
            assert deleted == [
                f"{FOLDER_PATH}/{CRUD_RELEASE_ID}/instances/20",
                f"{FOLDERS_PATH}/{SCRATCH_FOLDER_ID}",
            ]

    def test_instance_already_gone_does_not_stop_the_sweep(self, client, sleeps):
        """A stale listing can still show the copy the test just removed."""
        with mock_router() as router:
            router.get(FOLDERS_PATH).respond(
                200,
                json={
                    "folders": [
                        make_collection_folder(id=1, name="Uncategorized"),
                        make_collection_folder(id=7, name="Vinyl"),
                        make_collection_folder(
                            id=SCRATCH_FOLDER_ID, name=f"{TEST_FOLDER_PREFIX} scratch"
                        ),
                    ]
                },
            )
            router.get(FOLDER_PATH).mock(
                side_effect=in_turn(
                    make_paginated_response("releases", [CREATED_INSTANCE]),
                    make_paginated_response("releases", []),
                )
            )
            router.delete(f"{FOLDER_PATH}/{CRUD_RELEASE_ID}/instances/20").respond(
                404, json={"message": "Instance not found."}
            )
            router.delete(f"{FOLDERS_PATH}/{SCRATCH_FOLDER_ID}").respond(204)

            delete_test_folders(client, USERNAME)

            deleted = [
                call.request.url.path
                for call in router.calls
                if call.request.method == "DELETE"
            ]
            assert deleted == [
                f"{FOLDER_PATH}/{CRUD_RELEASE_ID}/instances/20",
                f"{FOLDERS_PATH}/{SCRATCH_FOLDER_ID}",
            ]
            assert sleeps == []

    def test_folder_that_never_shows_empty_is_left_for_the_next_run(
        self, client, sleeps
    ):
        with mock_router(assert_all_called=False) as router:
            router.get(FOLDERS_PATH).respond(
                200,
                json={
                    "folders": [
                        make_collection_folder(
                            id=SCRATCH_FOLDER_ID, name=f"{TEST_FOLDER_PREFIX} scratch"
                        )
                    ]
                },
            )
            router.get(FOLDER_PATH).respond(
                200, json=make_paginated_response("releases", [CREATED_INSTANCE])
            )
            router.delete(f"{FOLDER_PATH}/{CRUD_RELEASE_ID}/instances/20").respond(204)
            folder_deleted = router.delete(
                f"{FOLDERS_PATH}/{SCRATCH_FOLDER_ID}"
            ).respond(204)

            with pytest.raises(AssertionError, match=f"'{TEST_FOLDER_PREFIX} scratch'"):
                delete_test_folders(client, USERNAME)

            assert folder_deleted.call_count == 0
            assert sleeps == [10.0] * 5


class TestCollectionLifecycle:
    def test_deletes_only_the_instance_it_created(self, client, scratch_folder):
        with mock_router() as router:
            router.post(f"{FOLDER_PATH}/{CRUD_RELEASE_ID}").respond(
                201,
                json=make_collection_instance_created(
                    instance_id=20, release_id=CRUD_RELEASE_ID
                ),
            )
            router.get(FOLDER_PATH).respond(
                200,
                json=make_paginated_response(
                    "releases", [EXISTING_INSTANCE, CREATED_INSTANCE]
                ),
            )
            deleted = router.delete(
                f"{FOLDER_PATH}/{CRUD_RELEASE_ID}/instances/20"
            ).respond(204)

            collection_workflow.TestCollectionReleases().test_add_and_remove_release(
                client, USERNAME, scratch_folder
            )

            assert deleted.call_count == 1
            # The pre-existing copy, with its notes and rating, was never touched.
            deleted_paths = [
                call.request.url.path
                for call in router.calls
                if call.request.method == "DELETE"
            ]
            assert deleted_paths == [f"{FOLDER_PATH}/{CRUD_RELEASE_ID}/instances/20"]

    def test_waits_for_a_listing_that_lags_behind_the_create(
        self, client, scratch_folder, sleeps
    ):
        with mock_router() as router:
            router.post(f"{FOLDER_PATH}/{CRUD_RELEASE_ID}").respond(
                201,
                json=make_collection_instance_created(
                    instance_id=20, release_id=CRUD_RELEASE_ID
                ),
            )
            router.get(FOLDER_PATH).mock(
                side_effect=in_turn(
                    make_paginated_response("releases", [EXISTING_INSTANCE]),
                    make_paginated_response("releases", [EXISTING_INSTANCE]),
                    make_paginated_response(
                        "releases", [EXISTING_INSTANCE, CREATED_INSTANCE]
                    ),
                )
            )
            deleted = router.delete(
                f"{FOLDER_PATH}/{CRUD_RELEASE_ID}/instances/20"
            ).respond(204)

            collection_workflow.TestCollectionReleases().test_add_and_remove_release(
                client, USERNAME, scratch_folder
            )

            assert deleted.call_count == 1
            assert sleeps == [10.0] * 2

    def test_verification_failure_still_removes_only_the_created_instance(
        self, client, scratch_folder, sleeps
    ):
        with mock_router() as router:
            router.post(f"{FOLDER_PATH}/{CRUD_RELEASE_ID}").respond(
                201,
                json=make_collection_instance_created(
                    instance_id=20, release_id=CRUD_RELEASE_ID
                ),
            )
            # The new instance is missing from the listing, so verification fails.
            router.get(FOLDER_PATH).respond(
                200, json=make_paginated_response("releases", [EXISTING_INSTANCE])
            )
            deleted = router.delete(
                f"{FOLDER_PATH}/{CRUD_RELEASE_ID}/instances/20"
            ).respond(204)

            with pytest.raises(AssertionError, match="never showed up"):
                collection_workflow.TestCollectionReleases().test_add_and_remove_release(
                    client, USERNAME, scratch_folder
                )

            assert deleted.call_count == 1
            assert sleeps == [10.0] * 5

    def test_failed_creation_deletes_nothing(self, client, scratch_folder):
        with mock_router() as router:
            router.post(f"{FOLDER_PATH}/{CRUD_RELEASE_ID}").mock(
                return_value=respx.MockResponse(
                    422, json={"message": "Cannot add to this folder"}
                )
            )

            with pytest.raises(Exception, match="Cannot add to this folder"):
                collection_workflow.TestCollectionReleases().test_add_and_remove_release(
                    client, USERNAME, scratch_folder
                )

            assert [call.request.method for call in router.calls] == ["POST"]


class TestFolderLifecycle:
    def test_waits_for_a_folder_listing_that_lags_behind_the_create(
        self, client, sleeps
    ):
        created = make_collection_folder(
            id=99, name=f"{TEST_FOLDER_PREFIX} lifecycle", count=0
        )
        existing = [
            make_collection_folder(id=0, name="All"),
            make_collection_folder(id=1, name="Uncategorized"),
        ]
        with mock_router() as router:
            router.post(FOLDERS_PATH).respond(201, json=created)
            router.get(FOLDERS_PATH).mock(
                side_effect=in_turn(
                    {"folders": existing}, {"folders": [*existing, created]}
                )
            )
            router.delete(f"{FOLDERS_PATH}/99").respond(204)

            collection_workflow.TestCollectionFolders().test_create_list_delete_folder(
                client, USERNAME
            )

            deleted = [
                call.request.url.path
                for call in router.calls
                if call.request.method == "DELETE"
            ]
            assert deleted == [f"{FOLDERS_PATH}/99"]
            assert sleeps == [10.0]


WANTLIST_PATH = f"/users/{USERNAME}/wants"

EXISTING_WANT = {
    "id": CRUD_RELEASE_ID,
    "rating": 4,
    "notes": "Looking for the original pressing",
    "basic_information": {"id": CRUD_RELEASE_ID, "title": "Pretty Hate Machine"},
}
LEFTOVER_WANT = {
    "id": CRUD_RELEASE_ID,
    "notes": WANT_MARKER,
    "basic_information": {"id": CRUD_RELEASE_ID, "title": "Pretty Hate Machine"},
}


class TestWantlistLifecycle:
    def test_pre_existing_want_survives_unchanged(self, client, monkeypatch):
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        with mock_router() as router:
            router.get(WANTLIST_PATH).respond(
                200, json=make_paginated_response("wants", [EXISTING_WANT])
            )

            with pytest.raises(Skipped):
                wantlist_workflow.TestWantlistCRUD().test_add_list_delete(
                    client, USERNAME
                )

            # No mutation was attempted against the user's existing want.
            assert {call.request.method for call in router.calls} == {"GET"}

    def test_pre_existing_want_fails_the_run_in_the_scheduled_job(
        self, client, monkeypatch
    ):
        """A skip here would leave the scheduled job green and untested."""
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        with mock_router() as router:
            router.get(WANTLIST_PATH).respond(
                200, json=make_paginated_response("wants", [EXISTING_WANT])
            )

            with pytest.raises(Failed):
                wantlist_workflow.TestWantlistCRUD().test_add_list_delete(
                    client, USERNAME
                )

            assert {call.request.method for call in router.calls} == {"GET"}

    def test_absent_want_completes_the_cycle_and_leaves_nothing_behind(self, client):
        with mock_router() as router:
            router.get(WANTLIST_PATH).mock(
                side_effect=in_turn(
                    make_paginated_response("wants", []),
                    make_paginated_response("wants", [{"id": CRUD_RELEASE_ID}]),
                )
            )
            created = router.put(f"{WANTLIST_PATH}/{CRUD_RELEASE_ID}").respond(
                201, json={"id": CRUD_RELEASE_ID, "notes": ""}
            )
            tagged = router.post(f"{WANTLIST_PATH}/{CRUD_RELEASE_ID}").respond(
                200, json=LEFTOVER_WANT
            )
            deleted = router.delete(f"{WANTLIST_PATH}/{CRUD_RELEASE_ID}").respond(204)

            wantlist_workflow.TestWantlistCRUD().test_add_list_delete(client, USERNAME)

            assert created.call_count == 1
            assert tagged.call_count == 1
            assert deleted.call_count == 1

    def test_tagging_failure_still_removes_the_new_want(self, client):
        """A want that was created must not survive a failure of the next call."""
        with mock_router() as router:
            router.get(WANTLIST_PATH).respond(
                200, json=make_paginated_response("wants", [])
            )
            router.put(f"{WANTLIST_PATH}/{CRUD_RELEASE_ID}").respond(
                201, json={"id": CRUD_RELEASE_ID, "notes": ""}
            )
            router.post(f"{WANTLIST_PATH}/{CRUD_RELEASE_ID}").mock(
                return_value=respx.MockResponse(500, json={"message": "boom"})
            )
            deleted = router.delete(f"{WANTLIST_PATH}/{CRUD_RELEASE_ID}").respond(204)

            with pytest.raises(Exception, match="boom"):
                wantlist_workflow.TestWantlistCRUD().test_add_list_delete(
                    client, USERNAME
                )

            assert deleted.call_count == 1

    def test_want_that_never_shows_up_fails_and_is_still_removed(self, client, sleeps):
        with mock_router() as router:
            # Every read, the pre-check and each poll alike, comes back empty.
            router.get(WANTLIST_PATH).respond(
                200, json=make_paginated_response("wants", [])
            )
            router.put(f"{WANTLIST_PATH}/{CRUD_RELEASE_ID}").respond(
                201, json={"id": CRUD_RELEASE_ID, "notes": ""}
            )
            router.post(f"{WANTLIST_PATH}/{CRUD_RELEASE_ID}").respond(
                200, json=LEFTOVER_WANT
            )
            deleted = router.delete(f"{WANTLIST_PATH}/{CRUD_RELEASE_ID}").respond(204)

            with pytest.raises(AssertionError, match="never showed up"):
                wantlist_workflow.TestWantlistCRUD().test_add_list_delete(
                    client, USERNAME
                )

            assert deleted.call_count == 1
            # Every attempt but the last is followed by eventually()'s delay.
            assert sleeps == [10.0] * 5

    def test_own_leftover_want_is_reclaimed_rather_than_blocking_the_run(self, client):
        """A want the suite tagged is debris from a killed run, not user data."""
        with mock_router() as router:
            router.get(WANTLIST_PATH).respond(
                200, json=make_paginated_response("wants", [LEFTOVER_WANT])
            )
            created = router.put(f"{WANTLIST_PATH}/{CRUD_RELEASE_ID}").respond(
                201, json=LEFTOVER_WANT
            )
            tagged = router.post(f"{WANTLIST_PATH}/{CRUD_RELEASE_ID}").respond(
                200, json=LEFTOVER_WANT
            )
            deleted = router.delete(f"{WANTLIST_PATH}/{CRUD_RELEASE_ID}").respond(204)

            wantlist_workflow.TestWantlistCRUD().test_add_list_delete(client, USERNAME)

            assert created.call_count == 1
            assert tagged.call_count == 1
            assert deleted.call_count == 1
