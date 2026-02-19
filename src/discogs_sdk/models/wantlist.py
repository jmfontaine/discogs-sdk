from __future__ import annotations

from discogs_sdk.models._common import BasicInformation, SDKModel


class Want(SDKModel):
    id: int
    basic_information: BasicInformation | None = None
    notes: str | None = None
    rating: int | None = None
    resource_url: str | None = None
