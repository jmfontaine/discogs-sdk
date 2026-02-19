"""Tests for sync Collection resource."""

from __future__ import annotations

import httpx
import pytest

from discogs_sdk._exceptions import NotFoundError
from discogs_sdk.models.collection import (
    CollectionField,
    CollectionFolder,
    CollectionItem,
)

from tests.conftest import (
    make_collection_field,
    make_collection_folder,
    make_collection_item,
    make_collection_value,
    make_paginated_response,
)


class TestCollectionFoldersList:
    def test_returns_list_not_page(self, client, respx_mock):
        """Non-paginated: returns list[CollectionFolder], not SyncPage."""
        respx_mock.get("/users/trent_reznor/collection/folders").mock(
            return_value=httpx.Response(
                200,
                json={"folders": [make_collection_folder(id=0), make_collection_folder(id=1, name="Custom")]},
            )
        )
        lazy = client.users.get("trent_reznor")
        result = lazy.collection.folders.list()
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(f, CollectionFolder) for f in result)


class TestCollectionFoldersGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        lazy = client.users.get("trent_reznor")
        _folder = lazy.collection.folders.get(0)
        assert respx_mock.calls.call_count == 0

    def test_get_resolves(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/collection/folders/0").mock(
            return_value=httpx.Response(200, json=make_collection_folder())
        )
        lazy = client.users.get("trent_reznor")
        folder = lazy.collection.folders.get(0)
        assert folder.name == "All"


class TestCollectionFoldersCRUD:
    def test_create(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor/collection/folders").mock(
            return_value=httpx.Response(201, json=make_collection_folder(id=2, name="New"))
        )
        lazy = client.users.get("trent_reznor")
        result = lazy.collection.folders.create(name="New")
        assert result.name == "New"

    def test_update(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor/collection/folders/2").mock(
            return_value=httpx.Response(200, json=make_collection_folder(id=2, name="Renamed"))
        )
        lazy = client.users.get("trent_reznor")
        result = lazy.collection.folders.update(2, name="Renamed")
        assert result.name == "Renamed"

    def test_delete(self, client, respx_mock):
        respx_mock.delete("/users/trent_reznor/collection/folders/2").mock(return_value=httpx.Response(204))
        lazy = client.users.get("trent_reznor")
        lazy.collection.folders.delete(2)

    def test_delete_error(self, client, respx_mock):
        respx_mock.delete("/users/trent_reznor/collection/folders/999").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        lazy = client.users.get("trent_reznor")
        with pytest.raises(NotFoundError):
            lazy.collection.folders.delete(999)


class TestFolderReleases:
    def test_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/collection/folders/0/releases").mock(
            return_value=httpx.Response(
                200,
                json=make_paginated_response("releases", [make_collection_item()]),
            )
        )
        lazy = client.users.get("trent_reznor")
        folder = lazy.collection.folders.get(0)
        results = list(folder.releases.list())
        assert len(results) == 1
        assert isinstance(results[0], CollectionItem)

    def test_create(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor/collection/folders/1/releases/400027").mock(
            return_value=httpx.Response(201)
        )
        lazy = client.users.get("trent_reznor")
        folder = lazy.collection.folders.get(1)
        folder.releases.create(release_id=400027)

    def test_create_error(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor/collection/folders/1/releases/999").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        lazy = client.users.get("trent_reznor")
        folder = lazy.collection.folders.get(1)
        with pytest.raises(NotFoundError):
            folder.releases.create(release_id=999)


class TestDeepChaining:
    def test_deep_chain_no_http(self, client, respx_mock):
        """folders.get(3).releases.get(rid).instances.get(iid).fields — no HTTP."""
        lazy = client.users.get("trent_reznor")
        folder = lazy.collection.folders.get(3)
        release_ref = folder.releases.get(400027)
        instance_ref = release_ref.instances.get(42)
        _fields = instance_ref.fields
        assert respx_mock.calls.call_count == 0

    def test_instance_fields_update(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor/collection/folders/3/releases/400027/instances/42/fields/1").mock(
            return_value=httpx.Response(204)
        )
        lazy = client.users.get("trent_reznor")
        folder = lazy.collection.folders.get(3)
        ref = folder.releases.get(400027)
        instance = ref.instances.get(42)
        instance.fields.update(1, value="Mint (M)")

    def test_instance_fields_update_error(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor/collection/folders/3/releases/400027/instances/42/fields/1").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        lazy = client.users.get("trent_reznor")
        folder = lazy.collection.folders.get(3)
        instance = folder.releases.get(400027).instances.get(42)
        with pytest.raises(NotFoundError):
            instance.fields.update(1, value="Mint (M)")


class TestCollectionInstances:
    def test_update(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor/collection/folders/0/releases/400027/instances/1").mock(
            return_value=httpx.Response(204)
        )
        lazy = client.users.get("trent_reznor")
        folder = lazy.collection.folders.get(0)
        ref = folder.releases.get(400027)
        ref.instances.update(1, rating=4)

    def test_update_error(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor/collection/folders/0/releases/400027/instances/1").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        lazy = client.users.get("trent_reznor")
        folder = lazy.collection.folders.get(0)
        ref = folder.releases.get(400027)
        with pytest.raises(NotFoundError):
            ref.instances.update(1, rating=4)

    def test_delete(self, client, respx_mock):
        respx_mock.delete("/users/trent_reznor/collection/folders/0/releases/400027/instances/1").mock(
            return_value=httpx.Response(204)
        )
        lazy = client.users.get("trent_reznor")
        folder = lazy.collection.folders.get(0)
        ref = folder.releases.get(400027)
        ref.instances.delete(1)

    def test_delete_error(self, client, respx_mock):
        respx_mock.delete("/users/trent_reznor/collection/folders/0/releases/400027/instances/1").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        lazy = client.users.get("trent_reznor")
        folder = lazy.collection.folders.get(0)
        ref = folder.releases.get(400027)
        with pytest.raises(NotFoundError):
            ref.instances.delete(1)


class TestCollectionReleases:
    def test_cross_folder_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/collection/releases/400027").mock(
            return_value=httpx.Response(
                200,
                json=make_paginated_response("releases", [make_collection_item()]),
            )
        )
        lazy = client.users.get("trent_reznor")
        ref = lazy.collection.releases.get(400027)
        results = list(ref.list())
        assert len(results) == 1
        assert isinstance(results[0], CollectionItem)


class TestCollectionFields:
    def test_list_returns_list_not_page(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/collection/fields").mock(
            return_value=httpx.Response(200, json={"fields": [make_collection_field()]})
        )
        lazy = client.users.get("trent_reznor")
        result = lazy.collection.fields.list()
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], CollectionField)


class TestCollectionValue:
    def test_get(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/collection/value").mock(
            return_value=httpx.Response(200, json=make_collection_value())
        )
        lazy = client.users.get("trent_reznor")
        result = lazy.collection.value.get()
        assert result.median == "$10.00"
