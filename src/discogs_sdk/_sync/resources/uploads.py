# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations

import os

from discogs_sdk._base_client import job_id_from_location, path_segment
from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models._lazy_fields import UploadFields
from discogs_sdk.models.upload import Upload


class UploadProxy(LazyResource[Upload], UploadFields):
    """Lazy inventory upload."""


class Uploads(SyncAPIResource):
    def create(self, *, file: str | os.PathLike[str]) -> int:
        """Upload a CSV of listings to add and return the new job's id.

        Pass the id to ``get()`` to follow the job. It comes from the response's
        ``Location`` header; when that is missing or does not end in an integer,
        ``DiscogsAPIError`` is raised with the response's status and text. Discogs
        accepted the file, so the job probably exists: find it with ``list()``
        rather than uploading again. An error status raises its usual exception.
        """
        return self._submit("/inventory/upload/add", file)

    def change(self, *, file: str | os.PathLike[str]) -> int:
        """Upload a CSV of listing changes and return the new job's id.

        The id and its errors work as in ``create()``.
        """
        return self._submit("/inventory/upload/change", file)

    def delete(self, *, file: str | os.PathLike[str]) -> int:
        """Upload a CSV of listings to delete and return the new job's id.

        The id and its errors work as in ``create()``.
        """
        return self._submit("/inventory/upload/delete", file)

    def _submit(self, path: str, file: str | os.PathLike[str]) -> int:
        response = self._post_file(path, file_path=file)
        return job_id_from_location(response, listing="uploads.list()")

    def list(
        self, *, page: int | None = None, per_page: int | None = None
    ) -> SyncPage[Upload]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return SyncPage(
            client=self._client,
            items_key="items",
            model_cls=Upload,
            params=params,
            path="/inventory/upload",
        )

    def get(self, upload_id: int) -> UploadProxy:
        """Lazy upload status. Its request bypasses the response cache, so every
        new proxy sees the current status; a resolved proxy keeps its data, so poll
        with a new ``get()`` call each time."""
        return UploadProxy(
            self._client,
            f"/inventory/upload/{path_segment(upload_id)}",
            Upload,
            cacheable=False,
        )
