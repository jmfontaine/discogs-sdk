# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from discogs_sdk._sync._client import Discogs
_M = TypeVar("_M", bound=BaseModel)


class LazyResource(Generic[_M]):
    """Proxy that defers the HTTP call until explicitly awaited (async)
    or until a data attribute is accessed (sync, via generated code).

    Sub-resource accessors are declared by concrete subclasses as properties, so
    they are typed and never trigger an HTTP call in either variant.

    The dynamic ``__getattr__`` fallback is hidden from type checkers: the data
    fields a consumer may read are declared on the generated field mixins, so a
    misspelled field is a static error instead of an ``Any``.
    """

    # Declared so subclasses can read them without falling through __getattr__,
    # which is deliberately invisible to type checkers.
    _client: Discogs
    _path: str
    _model_cls: type[_M]
    _params: dict[str, Any] | None

    def __init__(
        self, client: Discogs, path: str, model_cls: type[_M], *, params: dict[str, Any] | None = None
    ) -> None:
        self._client = client
        self._path = path
        self._model_cls = model_cls
        self._params = params
        # Written through object.__setattr__ and read through
        # object.__getattribute__: a plain read would recurse through __getattr__.
        object.__setattr__(self, "_resolved", None)

    def _resolve(self) -> _M:
        # Read through object.__getattribute__: a plain attribute read on a subclass
        # that has not finished __init__ would fall through to __getattr__ and fetch.
        resolved = object.__getattribute__(self, "_resolved")
        if resolved is not None:
            return resolved
        client = object.__getattribute__(self, "_client")
        path = object.__getattribute__(self, "_path")
        model_cls = object.__getattribute__(self, "_model_cls")
        params = object.__getattribute__(self, "_params")
        response = client._send("GET", client._build_url(path), params=params)
        resolved = model_cls.model_validate(response.json())
        object.__setattr__(self, "_resolved", resolved)
        return resolved

    if not TYPE_CHECKING:

        def __getattr__(self, name: str) -> Any:
            # Otherwise, resolve the model via HTTP and delegate
            model = self._resolve()
            return getattr(model, name)

        def __getitem__(self, key: str) -> Any:
            resolved = self._resolve()
            getter = getattr(resolved, "__getitem__", None)
            if getter is None:
                raise TypeError(f"'{type(resolved).__name__}' object is not subscriptable")
            return getter(key)

    def __repr__(self) -> str:
        path = object.__getattribute__(self, "_path")
        model_cls = object.__getattribute__(self, "_model_cls")
        resolved = object.__getattribute__(self, "_resolved")
        if resolved is not None:
            return repr(resolved)
        return f"<LazyResource {model_cls.__name__} path={path!r}>"
