from __future__ import annotations

if True:  # ASYNC
    import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

import httpx2
from pydantic import BaseModel

if TYPE_CHECKING:
    from discogs_sdk._async._client import AsyncDiscogs

_M = TypeVar("_M", bound=BaseModel)


class AsyncAPIResource:
    def __init__(self, client: AsyncDiscogs) -> None:
        self._client = client

    async def _get_list(
        self, path: str, model_cls: type[_M], items_key: str
    ) -> list[_M]:
        """GET a keyed array and return it validated.

        Validation runs inside ``_send``, so a body that fails is never cached and
        a cached one that fails is never served.
        """

        def parse(data: Any) -> list[_M]:
            return [model_cls.model_validate(item) for item in data.get(items_key, [])]

        return await self._client._send(
            "GET", self._client._build_url(path), parse=parse
        )

    def _parse_response(self, response: httpx2.Response, model_cls: type[_M]) -> _M:
        """Return a validated model. Failures already raised in ``_send``."""
        return model_cls.model_validate(response.json())

    async def _delete(self, path: str) -> httpx2.Response:
        return await self._request("DELETE", path)

    async def _get_binary(self, path: str) -> bytes:
        response = await self._client._send("GET", self._client._build_url(path))
        return response.content

    async def _post(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx2.Response:
        return await self._request("POST", path, json=json, params=params)

    async def _post_file(
        self, path: str, *, file_path: str | os.PathLike[str]
    ) -> httpx2.Response:
        p = Path(file_path)
        if True:  # ASYNC
            # Reading a whole CSV would stall every task on the loop.
            data = await asyncio.to_thread(p.read_bytes)
        else:
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
    ) -> httpx2.Response:
        return await self._request("PUT", path, json=json, params=params)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx2.Response:
        return await self._client._send(
            method,
            self._client._build_url(path),
            json=json,
            params=params,
        )
