from __future__ import annotations

from pydantic import Field

from discogs_sdk.models._common import SDKModel


class Upload(SDKModel):
    id: int
    created_at: str | None = Field(default=None, validation_alias="created_ts")
    filename: str | None = None
    finished_at: str | None = Field(default=None, validation_alias="finished_ts")
    # A completed upload reports a summary string that may contain HTML markup.
    results: str | None = None
    status: str | None = None
    type: str | None = None
