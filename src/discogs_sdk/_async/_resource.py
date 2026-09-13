from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

import httpx
from pydantic import BaseModel

if TYPE_CHECKING:
    from discogs_sdk._async._client import AsyncDiscogs

_M = TypeVar("_M", bound=BaseModel)


class AsyncAPIResource:
    def __init__(self, client: AsyncDiscogs) -> None:
        self._client = client

    def _parse_list_response(self, response: httpx.Response, model_cls: type[_M], items_key: str) -> list[_M]:
        """Return a validated list from a keyed array. Failures already raised in ``_send``."""
        data = response.json()
        return [model_cls.model_validate(item) for item in data.get(items_key, [])]

    def _parse_response(self, response: httpx.Response, model_cls: type[_M]) -> _M:
        """Return a validated model. Failures already raised in ``_send``."""
        return model_cls.model_validate(response.json())

    async def _delete(self, path: str) -> httpx.Response:
        return await self._request("DELETE", path)

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> httpx.Response:
        return await self._request("GET", path, params=params)

    async def _get_binary(self, path: str) -> bytes:
        response = await self._client._send("GET", self._client._build_url(path))
        return response.content

    async def _post(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        return await self._request("POST", path, json=json, params=params)

    async def _post_file(self, path: str, *, file_path: str) -> httpx.Response:
        p = Path(file_path)
        data = p.read_bytes()
        return await self._client._send(
            "POST",
            self._client._build_url(path),
            files={"upload": (p.name, data, "text/csv")},
        )

    async def _put(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        return await self._request("PUT", path, json=json, params=params)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        return await self._client._send(
            method,
            self._client._build_url(path),
            json=json,
            params=params,
        )
