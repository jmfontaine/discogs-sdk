from __future__ import annotations

from typing import Any

from pydantic import Field

from discogs_sdk.models._common import SDKModel


class Upload(SDKModel):
    id: int
    created_at: str | None = Field(default=None, validation_alias="created_ts")
    filename: str | None = None
    finished_at: str | None = Field(default=None, validation_alias="finished_ts")
    results: dict[str, Any] | None = None
    status: str | None = None
    type: str | None = None
