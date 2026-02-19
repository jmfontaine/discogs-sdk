# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations
import builtins
from functools import cached_property
from typing import TYPE_CHECKING, Any
from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models.collection import CollectionField, CollectionFolder, CollectionItem, CollectionValue_

if TYPE_CHECKING:
    from discogs_sdk._sync._client import Discogs
# --- Deep chaining: folder -> releases -> instances -> fields ---


class InstanceFields(SyncAPIResource):
    """Edit a custom field value on a specific instance."""

    def __init__(self, client, username: str, folder_id: int, release_id: int, instance_id: int) -> None:
        super().__init__(client)
        self._username = username
        self._folder_id = folder_id
        self._release_id = release_id
        self._instance_id = instance_id

    def update(self, field_id: int, *, value: str) -> None:
        response = self._post(
            f"/users/{self._username}/collection/folders/{self._folder_id}/releases/{self._release_id}/instances/{self._instance_id}/fields/{field_id}",
            json={"value": value},
        )
        self._raise_for_error(response)


class InstanceRef:
    """Lightweight ref that captures instance_id for field editing."""

    def __init__(self, client: Discogs, username: str, folder_id: int, release_id: int, instance_id: int) -> None:
        self._client = client
        self._username = username
        self._folder_id = folder_id
        self._release_id = release_id
        self._instance_id = instance_id

    @cached_property
    def fields(self) -> InstanceFields:
        return InstanceFields(self._client, self._username, self._folder_id, self._release_id, self._instance_id)


class CollectionInstances(SyncAPIResource):
    """Manage instances of a release within a folder."""

    def __init__(self, client, username: str, folder_id: int, release_id: int) -> None:
        super().__init__(client)
        self._username = username
        self._folder_id = folder_id
        self._release_id = release_id

    def _base_path(self) -> str:
        return f"/users/{self._username}/collection/folders/{self._folder_id}/releases/{self._release_id}/instances"

    def get(self, instance_id: int) -> InstanceRef:
        return InstanceRef(self._client, self._username, self._folder_id, self._release_id, instance_id)

    def delete(self, instance_id: int) -> None:
        response = self._delete(f"{self._base_path()}/{instance_id}")
        self._raise_for_error(response)

    def update(self, instance_id: int, **kwargs: Any) -> None:
        response = self._post(f"{self._base_path()}/{instance_id}", json=kwargs)
        self._raise_for_error(response)


class FolderReleaseRef:
    """Lightweight ref for a release within a folder — provides .instances accessor."""

    def __init__(self, client: Discogs, username: str, folder_id: int, release_id: int) -> None:
        self._client = client
        self._username = username
        self._folder_id = folder_id
        self._release_id = release_id

    @cached_property
    def instances(self) -> CollectionInstances:
        return CollectionInstances(self._client, self._username, self._folder_id, self._release_id)


class FolderReleases(SyncAPIResource):
    """Items in a collection folder."""

    def __init__(self, client, username: str, folder_id: int) -> None:
        super().__init__(client)
        self._username = username
        self._folder_id = folder_id

    def _base_path(self) -> str:
        return f"/users/{self._username}/collection/folders/{self._folder_id}/releases"

    def get(self, release_id: int) -> FolderReleaseRef:
        return FolderReleaseRef(self._client, self._username, self._folder_id, release_id)

    def list(self, *, sort: str | None = None, sort_order: str | None = None) -> SyncPage[CollectionItem]:
        params = {k: v for k, v in {"sort": sort, "sort_order": sort_order}.items() if v}
        return SyncPage(
            client=self._client, items_key="releases", model_cls=CollectionItem, params=params, path=self._base_path()
        )

    def create(self, *, release_id: int) -> None:
        response = self._post(f"{self._base_path()}/{release_id}")
        self._raise_for_error(response)


# --- Collection Folders ---


class CollectionFolders(SyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def _base_path(self) -> str:
        return f"/users/{self._username}/collection/folders"

    def get(self, folder_id: int) -> LazyResource:
        return LazyResource(
            client=self._client,
            path=f"{self._base_path()}/{folder_id}",
            model_cls=CollectionFolder,
            sub_resources={"releases": lambda: FolderReleases(self._client, self._username, folder_id)},
        )

    def list(self) -> builtins.list[CollectionFolder]:
        response = self._get(self._base_path())
        return self._parse_list_response(response, CollectionFolder, "folders")

    def create(self, *, name: str) -> CollectionFolder:
        response = self._post(self._base_path(), json={"name": name})
        return self._parse_response(response, CollectionFolder)

    def delete(self, folder_id: int) -> None:
        response = self._delete(f"{self._base_path()}/{folder_id}")
        self._raise_for_error(response)

    def update(self, folder_id: int, *, name: str) -> CollectionFolder:
        response = self._post(f"{self._base_path()}/{folder_id}", json={"name": name})
        return self._parse_response(response, CollectionFolder)


# --- Collection Releases (cross-folder) ---


class CollectionReleaseRef:
    """Ref for a release across all folders. Provides .list() for instances."""

    def __init__(self, client: Discogs, username: str, release_id: int) -> None:
        self._client = client
        self._username = username
        self._release_id = release_id

    def list(self) -> SyncPage[CollectionItem]:
        return SyncPage(
            client=self._client,
            items_key="releases",
            model_cls=CollectionItem,
            path=f"/users/{self._username}/collection/releases/{self._release_id}",
        )


class CollectionReleases(SyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def get(self, release_id: int) -> CollectionReleaseRef:
        return CollectionReleaseRef(self._client, self._username, release_id)


# --- Collection Fields ---


class CollectionFields(SyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def list(self) -> builtins.list[CollectionField]:
        response = self._get(f"/users/{self._username}/collection/fields")
        return self._parse_list_response(response, CollectionField, "fields")


# --- Collection Value ---


class CollectionValueResource(SyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def get(self) -> LazyResource:
        return LazyResource(
            client=self._client, model_cls=CollectionValue_, path=f"/users/{self._username}/collection/value"
        )


# --- Collection namespace ---


class Collection:
    def __init__(self, client: Discogs, username: str) -> None:
        self._client = client
        self._username = username

    @cached_property
    def fields(self) -> CollectionFields:
        return CollectionFields(self._client, self._username)

    @cached_property
    def folders(self) -> CollectionFolders:
        return CollectionFolders(self._client, self._username)

    @cached_property
    def releases(self) -> CollectionReleases:
        return CollectionReleases(self._client, self._username)

    @cached_property
    def value(self) -> CollectionValueResource:
        return CollectionValueResource(self._client, self._username)
