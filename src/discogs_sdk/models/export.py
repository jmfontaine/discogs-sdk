from __future__ import annotations

from pydantic import Field

from discogs_sdk.models._common import SDKModel


class Export(SDKModel):
    id: int
    created_at: str | None = Field(default=None, validation_alias="created_ts")
    download_url: str | None = None
    filename: str | None = None
    finished_at: str | None = Field(default=None, validation_alias="finished_ts")
    status: str | None = None
    url: str | None = None
