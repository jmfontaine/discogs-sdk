from __future__ import annotations

if True:  # ASYNC
    import asyncio
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from discogs_sdk._async._client import AsyncDiscogs

_M = TypeVar("_M", bound=BaseModel)


class AsyncLazyResource(Generic[_M]):
    """Proxy that defers the HTTP call until explicitly awaited (async)
    or until a data attribute is accessed (sync, via generated code).

    Sub-resource accessors are declared by concrete subclasses as properties, so
    they are typed and never trigger an HTTP call in either variant.

    Names beginning with ``_`` never trigger an HTTP call either: no data field
    starts with one, so the sync proxy raises ``AttributeError`` for them, resolved
    or not, instead of fetching the model to answer a tool's probe.

    Proxies are read-only views. Assigning a name that does not begin with ``_``
    raises ``AttributeError``, before or after resolution, because the value would
    never reach Discogs and would shadow the model's own for every later read.

    The dynamic ``__getattr__`` fallback is hidden from type checkers: the data
    fields a consumer may read are declared on the generated field mixins, so a
    misspelled field is a static error instead of an ``Any``.
    """

    # Declared so subclasses can read them without falling through __getattr__,
    # which is deliberately invisible to type checkers.
    _client: AsyncDiscogs
    _path: str
    _model_cls: type[_M]
    _params: dict[str, Any] | None
    _cacheable: bool

    def __init__(
        self,
        client: AsyncDiscogs,
        path: str,
        model_cls: type[_M],
        *,
        params: dict[str, Any] | None = None,
        cacheable: bool = True,
    ) -> None:
        """*cacheable* ``False`` sends the request past the response cache, for a
        resource whose data changes while a cached copy would still be fresh."""
        self._client = client
        self._path = path
        self._model_cls = model_cls
        self._params = params
        self._cacheable = cacheable
        # Written through object.__setattr__ and read through
        # object.__getattribute__: a plain read would recurse through __getattr__.
        object.__setattr__(self, "_resolved", None)
        if True:  # ASYNC
            # The fetch shared by every awaiter while the proxy is unresolved; set
            # only while that request is pending.
            object.__setattr__(self, "_inflight", None)

    async def _resolve(self) -> _M:
        # Read through object.__getattribute__: a plain attribute read on a subclass
        # that has not finished __init__ would fall through to __getattr__ and fetch.
        resolved = object.__getattribute__(self, "_resolved")
        if resolved is not None:
            return resolved
        if True:  # ASYNC
            # Single flight: the first awaiter starts the request as a task and
            # every awaiter, that one included, waits for it with asyncio.wait(),
            # which never cancels what it waits on, so cancelling one waiter
            # neither cancels the request nor affects the others. Not shield():
            # some releases from 3.14 on (seen on 3.14.2) log the request's
            # exception when every waiter was cancelled. The task copies the first
            # awaiter's context, so its no_cache()/cache_only() scope applies to
            # every awaiter it serves. A finished task is never reused, so a failure
            # is not cached even before its done callback has cleared the slot.
            inflight = object.__getattribute__(self, "_inflight")
            if inflight is None or inflight.done():
                inflight = asyncio.create_task(self._fetch())
                object.__setattr__(self, "_inflight", inflight)
                inflight.add_done_callback(self._fetch_done)
            await asyncio.wait((inflight,))
            return inflight.result()
        else:
            return self._fetch()

    async def _fetch(self) -> _M:
        client = object.__getattribute__(self, "_client")
        path = object.__getattribute__(self, "_path")
        model_cls = object.__getattribute__(self, "_model_cls")
        params = object.__getattribute__(self, "_params")
        cacheable = object.__getattribute__(self, "_cacheable")

        # Validated inside _send, so a body that fails is never cached and a
        # cached one that fails is never served.
        resolved = await client._send(
            "GET",
            client._build_url(path),
            params=params,
            cacheable=cacheable,
            parse=model_cls.model_validate,
        )
        object.__setattr__(self, "_resolved", resolved)
        return resolved

    if True:  # ASYNC

        def _fetch_done(self, task: asyncio.Task[_M]) -> None:
            # Drop the reference once the request settles, so a proxy resolved
            # under one event loop holds nothing tied to it, and a failed fetch
            # leaves the next await free to start a fresh one.
            if object.__getattribute__(self, "_inflight") is task:
                object.__setattr__(self, "_inflight", None)
            # Retrieve the exception: when every waiter was cancelled nobody else
            # does, and asyncio would log "Task exception was never retrieved".
            if not task.cancelled():
                task.exception()

    if not TYPE_CHECKING:

        def __getattr__(self, name: str) -> Any:
            if True:  # ASYNC
                # Already resolved (after await)? Delegate to model.
                resolved = object.__getattribute__(self, "_resolved")
                if resolved is not None:
                    return getattr(resolved, name)
                raise AttributeError(
                    f"Cannot access '{name}' on unresolved AsyncLazyResource. "
                    "Use: resolved = await resource"
                )
            else:
                # No data field starts with "_" (Pydantic makes such names private),
                # so a miss on one is a tool's probe (_repr_html_, __deepcopy__,
                # __html__) and must not spend a request.
                if name.startswith("_"):
                    raise AttributeError(name)
                # Resolve the model via HTTP and delegate.
                model = self._resolve()
                return getattr(model, name)

        # Hidden from type checkers like __getattr__: a declared __setattr__ would
        # make them accept assignment to any name, misspellings included.
        def __setattr__(self, name: str, value: Any) -> None:
            # An instance attribute would shadow the model for good, since
            # __getattr__ only runs on a miss. SDK state is all "_"-prefixed, and
            # cached_property writes to __dict__ directly, so neither comes here
            # with a public name.
            if not name.startswith("_"):
                raise AttributeError(f"Cannot set '{name}': lazy proxies are read-only")
            object.__setattr__(self, name, value)

        def __getitem__(self, key: str) -> Any:
            if True:  # ASYNC
                resolved = object.__getattribute__(self, "_resolved")
                if resolved is None:
                    raise TypeError(
                        "Cannot subscript unresolved AsyncLazyResource. "
                        "Use: resolved = await resource"
                    )
            else:
                resolved = self._resolve()
            getter = getattr(resolved, "__getitem__", None)
            if getter is None:
                raise TypeError(
                    f"'{type(resolved).__name__}' object is not subscriptable"
                )
            return getter(key)

    if True:  # ASYNC
        if TYPE_CHECKING:
            from collections.abc import Generator

        def __await__(self) -> Generator[Any, None, _M]:
            return self._resolve().__await__()

    def __repr__(self) -> str:
        path = object.__getattribute__(self, "_path")
        model_cls = object.__getattribute__(self, "_model_cls")
        resolved = object.__getattribute__(self, "_resolved")
        if resolved is not None:
            return repr(resolved)
        return f"<AsyncLazyResource {model_cls.__name__} path={path!r}>"
