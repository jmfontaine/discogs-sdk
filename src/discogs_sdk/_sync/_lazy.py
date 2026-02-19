# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Callable
from pydantic import BaseModel

if TYPE_CHECKING:
    from discogs_sdk._sync._client import Discogs


class LazyResource:
    """Proxy that defers the HTTP call until explicitly awaited (async)
    or until a data attribute is accessed (sync, via generated code).

    Sub-resource accessors (defined in ``sub_resources``) are returned
    immediately without triggering any HTTP call in both variants.
    """

    def __init__(
        self,
        client: Discogs,
        path: str,
        model_cls: type[BaseModel],
        sub_resources: dict[str, Callable[[], Any]] | None = None,
    ) -> None:
        # Use object.__setattr__ to bypass __getattr__, which would trigger _resolve() and defeat lazy loading
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_path", path)
        object.__setattr__(self, "_model_cls", model_cls)
        object.__setattr__(self, "_sub_resources", sub_resources or {})
        object.__setattr__(self, "_resolved", None)

    def _resolve(self) -> BaseModel:
        resolved = object.__getattribute__(self, "_resolved")
        if resolved is not None:
            return resolved
        client = object.__getattribute__(self, "_client")
        path = object.__getattribute__(self, "_path")
        model_cls = object.__getattribute__(self, "_model_cls")
        response = client._send("GET", client._build_url(path))
        body = response.json()
        client._maybe_raise(response.status_code, body, retry_after=response.headers.get("Retry-After"))
        resolved = model_cls.model_validate(body)
        object.__setattr__(self, "_resolved", resolved)
        return resolved

    def __getattr__(self, name: str) -> Any:
        # Check sub-resources first (no HTTP call)
        sub_resources = object.__getattribute__(self, "_sub_resources")
        if name in sub_resources:
            resource = sub_resources[name]()
            object.__setattr__(self, name, resource)
            return resource
        # Otherwise, resolve the model via HTTP and delegate
        model = self._resolve()
        return getattr(model, name)

    def __getitem__(self, key: str) -> Any:
        resolved = self._resolve()
        getter = getattr(resolved, "__getitem__", None)
        if getter is None:
            raise TypeError(f"'{type(resolved).__name__}' object is not subscriptable")
        return getter(key)  # pragma: no cover — no current model supports subscript

    def __repr__(self) -> str:
        path = object.__getattribute__(self, "_path")
        model_cls = object.__getattribute__(self, "_model_cls")
        resolved = object.__getattribute__(self, "_resolved")
        if resolved is not None:
            return repr(resolved)
        return f"<LazyResource {model_cls.__name__} path={path!r}>"
