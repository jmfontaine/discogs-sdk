"""The live integration workflows must not touch pre-existing user data.

These run the integration test bodies against HTTP mocks, so the destructive
paths are exercised without a real account.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from _pytest.outcomes import Skipped

from discogs_sdk import Discogs
from tests.conftest import (
    BASE_URL,
    make_collection_instance_created,
    make_paginated_response,
)
from tests.integration import test_collection as collection_workflow
from tests.integration import test_wantlist as wantlist_workflow
from tests.integration.conftest import CRUD_RELEASE_ID

USERNAME = "trent_reznor"
FOLDER_PATH = f"/users/{USERNAME}/collection/folders/1/releases"

EXISTING_INSTANCE = {
    "id": CRUD_RELEASE_ID,
    "instance_id": 10,
    "folder_id": 1,
    "rating": 5,
    "notes": [{"field_id": 1, "value": "First pressing, keep"}],
    "basic_information": {"id": CRUD_RELEASE_ID, "title": "Pretty Hate Machine"},
}
CREATED_INSTANCE = {
    "id": CRUD_RELEASE_ID,
    "instance_id": 20,
    "folder_id": 1,
    "basic_information": {"id": CRUD_RELEASE_ID, "title": "Pretty Hate Machine"},
}


@pytest.fixture
def client():
    with Discogs(token="test-token") as discogs:
        yield discogs


class TestCollectionLifecycle:
    def test_deletes_only_the_instance_it_created(self, client):
        with respx.mock(base_url=BASE_URL) as router:
            router.post(f"{FOLDER_PATH}/{CRUD_RELEASE_ID}").respond(
                201, json=make_collection_instance_created(instance_id=20, release_id=CRUD_RELEASE_ID)
            )
            router.get(FOLDER_PATH).respond(
                200,
                json=make_paginated_response("releases", [EXISTING_INSTANCE, CREATED_INSTANCE]),
            )
            deleted = router.delete(f"{FOLDER_PATH}/{CRUD_RELEASE_ID}/instances/20").respond(204)

            collection_workflow.TestCollectionReleases().test_add_and_remove_release(client, USERNAME)

            assert deleted.call_count == 1
            # The pre-existing copy, with its notes and rating, was never touched.
            deleted_paths = [call.request.url.path for call in router.calls if call.request.method == "DELETE"]
            assert deleted_paths == [f"{FOLDER_PATH}/{CRUD_RELEASE_ID}/instances/20"]

    def test_verification_failure_still_removes_only_the_created_instance(self, client):
        with respx.mock(base_url=BASE_URL) as router:
            router.post(f"{FOLDER_PATH}/{CRUD_RELEASE_ID}").respond(
                201, json=make_collection_instance_created(instance_id=20, release_id=CRUD_RELEASE_ID)
            )
            # The new instance is missing from the listing, so verification fails.
            router.get(FOLDER_PATH).respond(200, json=make_paginated_response("releases", [EXISTING_INSTANCE]))
            deleted = router.delete(f"{FOLDER_PATH}/{CRUD_RELEASE_ID}/instances/20").respond(204)

            with pytest.raises(AssertionError):
                collection_workflow.TestCollectionReleases().test_add_and_remove_release(client, USERNAME)

            assert deleted.call_count == 1

    def test_failed_creation_deletes_nothing(self, client):
        with respx.mock(base_url=BASE_URL) as router:
            router.post(f"{FOLDER_PATH}/{CRUD_RELEASE_ID}").mock(
                return_value=httpx.Response(422, json={"message": "Cannot add to this folder"})
            )

            with pytest.raises(Exception, match="Cannot add to this folder"):
                collection_workflow.TestCollectionReleases().test_add_and_remove_release(client, USERNAME)

            assert [call.request.method for call in router.calls] == ["POST"]


WANTLIST_PATH = f"/users/{USERNAME}/wants"

EXISTING_WANT = {
    "id": CRUD_RELEASE_ID,
    "rating": 4,
    "notes": "Looking for the original pressing",
    "basic_information": {"id": CRUD_RELEASE_ID, "title": "Pretty Hate Machine"},
}


class TestWantlistLifecycle:
    def test_pre_existing_want_survives_unchanged(self, client):
        with respx.mock(base_url=BASE_URL) as router:
            router.get(WANTLIST_PATH).respond(200, json=make_paginated_response("wants", [EXISTING_WANT]))

            with pytest.raises(Skipped):
                wantlist_workflow.TestWantlistCRUD().test_add_list_delete(client, USERNAME)

            # No mutation was attempted against the user's existing want.
            assert {call.request.method for call in router.calls} == {"GET"}

    def test_absent_want_completes_the_cycle_and_leaves_nothing_behind(self, client):
        with respx.mock(base_url=BASE_URL) as router:
            listings = iter(
                [
                    make_paginated_response("wants", []),
                    make_paginated_response("wants", [{"id": CRUD_RELEASE_ID}]),
                ]
            )
            router.get(WANTLIST_PATH).mock(side_effect=lambda req: httpx.Response(200, json=next(listings)))
            created = router.put(f"{WANTLIST_PATH}/{CRUD_RELEASE_ID}").respond(
                201, json={"id": CRUD_RELEASE_ID, "basic_information": {"id": CRUD_RELEASE_ID, "title": "PHM"}}
            )
            deleted = router.delete(f"{WANTLIST_PATH}/{CRUD_RELEASE_ID}").respond(204)

            wantlist_workflow.TestWantlistCRUD().test_add_list_delete(client, USERNAME)

            assert created.call_count == 1
            assert deleted.call_count == 1
