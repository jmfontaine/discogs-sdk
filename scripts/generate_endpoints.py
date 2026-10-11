#!/usr/bin/env python3
"""Generate ``docs/endpoints.md``: which SDK call reaches which Discogs endpoint.

One row per public SDK operation and route variant, with its HTTP verb, the call
chain from ``client``, the return type and whether the call returns a page.

This module is also the single extractor behind the route set that
``scripts/check_endpoint_coverage.py`` compares with the API reference
(``sdk_routes()``), so the map and that check cannot disagree about which routes
the SDK reaches. It reads only the SDK sources under ``src/discogs_sdk/``, never
the git-ignored reference, so it runs in CI.

How a method becomes rows. ``extract()`` interprets each public method of the
async resources with a small symbolic evaluator, following ``self`` helper calls
and constructors:

* a call to ``_get_list``/``_post``/``_put``/``_delete``/``_post_file``/``_get_binary``/
  ``_request``, a direct ``client._send(...)`` and, at module level, ``_send(...)``
  is a request with that verb and path;
* constructing an ``AsyncPage`` or a lazy proxy (``AsyncLazyResource`` subclass) is
  a ``GET`` of its path argument, resolved through the proxy's ``__init__``;
* local string variables are tracked through assignments, and an ``if`` that
  reassigns one yields both values, so a route built in several steps or
  conditionally yields every variant;
* ``self`` helpers (``_base_path()``, ``_user_path()``, ``_submit()``) are
  evaluated with the caller's arguments bound.

The access chain from ``client`` is derived from the properties and the
class-returning methods starting at ``AsyncDiscogs``. A resource class that no
chain reaches, or a public method that neither sends a request nor leads to
another class, stops the run with an error, so a new resource is never silently
left out.

Usage:
    python scripts/generate_endpoints.py           # write docs/endpoints.md
    python scripts/generate_endpoints.py --check   # fail when it is stale
"""

from __future__ import annotations

import argparse
import ast
import difflib
import itertools
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASYNC_SRC = ROOT / "src" / "discogs_sdk" / "_async"
OAUTH_PUBLIC = ROOT / "src" / "discogs_sdk" / "oauth.py"
OUTPUT = ROOT / "docs" / "endpoints.md"

CLIENT_CLASS = "AsyncDiscogs"
LAZY_BASE = "AsyncLazyResource"
PAGE_CLASS = "AsyncPage"
OAUTH_MODULE = "_oauth"

# Request helpers of ``AsyncAPIResource``: name -> verb. ``_request`` takes the
# verb as its first argument instead.
PRIMITIVES = {
    "_delete": "DELETE",
    "_get_list": "GET",
    "_get_binary": "GET",
    "_post": "POST",
    "_post_file": "POST",
    "_put": "PUT",
}

# Public methods of the client that send nothing and lead nowhere: they manage
# the cache and the connection. Anything else public must be classified.
NON_OPERATIONS = {
    (CLIENT_CLASS, "cache_only"),
    (CLIENT_CLASS, "clear_cache"),
    (CLIENT_CLASS, "close"),
    (CLIENT_CLASS, "no_cache"),
}

VERB_ORDER = {"GET": 0, "POST": 1, "PUT": 2, "DELETE": 3}
# Async names that have a different sync name in a return type. Everything else
# is a model, a builtin or a name shared by both clients.
SYNC_TYPE_NAMES = {PAGE_CLASS: "SyncPage"}

Values = frozenset[str]

# Marks a ``{name}`` that comes from an attribute of ``self`` (state set by the
# parent resource), so it is never mistaken for a call argument of the same name.
# ``Extractor`` strips it from the routes it returns.
ATTRIBUTE_MARK = "\x00"


class ExtractionError(Exception):
    """The sources hold something the extractor cannot classify."""


def normalise_route(path: str) -> str:
    """The comparison form of a route: every parameter becomes ``{}``."""
    path = re.sub(r"\{\?[^}]*\}", "", path)  # drop {?query,params} suffixes
    path = re.sub(r"\{[^}]*\}", "{}", path)  # collapse path parameters
    return path.split("?")[0].rstrip("/")


# --- Source model ----------------------------------------------------------

_Function = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass
class ClassInfo:
    name: str
    module: str
    node: ast.ClassDef
    methods: dict[str, _Function] = field(default_factory=dict)
    properties: set[str] = field(default_factory=set)
    bases: list[str] = field(default_factory=list)
    model: str | None = None  # the M of AsyncLazyResource[M], for a lazy proxy


@dataclass(frozen=True)
class Param:
    name: str
    required: bool
    keyword_only: bool


@dataclass(frozen=True)
class Request:
    verb: str
    route: str
    via: str | None  # the lazy proxy class this request constructs, if any


@dataclass
class Outcome:
    requests: set[Request] = field(default_factory=set)
    returns: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Ctx:
    cls: ClassInfo | None  # the receiver of ``self``; None at module level
    module: str
    depth: int = 0


@dataclass(frozen=True)
class Edge:
    """A step in an access chain: ``.name`` or ``.name(args)``."""

    text: str
    target: str


@dataclass(frozen=True)
class Row:
    verb: str
    route: str
    call: str
    returns: str
    paginated: bool


@dataclass(frozen=True)
class EndpointMap:
    operations: list[Row]
    oauth: list[Row]

    def routes(self) -> set[str]:
        """Every route as ``{}``-normalised templates."""
        return {normalise_route(row.route) for row in (*self.operations, *self.oauth)}


def _decorator_names(fn: _Function) -> set[str]:
    names: set[str] = set()
    for decorator in fn.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _is_self(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "self"


def _self_method(func: ast.expr) -> str | None:
    if isinstance(func, ast.Attribute) and _is_self(func.value):
        return func.attr
    return None


def _is_super_init(func: ast.expr) -> bool:
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "__init__"
        and isinstance(func.value, ast.Call)
        and isinstance(func.value.func, ast.Name)
        and func.value.func.id == "super"
    )


def _argument(call: ast.Call, index: int, name: str) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    if index < len(call.args) and not isinstance(call.args[index], ast.Starred):
        return call.args[index]
    return None


def _params(fn: _Function) -> tuple[list[Param], bool]:
    """The callable parameters (without ``self``) and whether it takes ``*``/``**``."""
    args = fn.args
    positional = [*args.posonlyargs, *args.args]
    if positional and positional[0].arg in ("self", "cls"):
        positional = positional[1:]
    first_default = len(positional) - len(args.defaults)
    params = [
        Param(arg.arg, index < first_default, False)
        for index, arg in enumerate(positional)
    ]
    params += [
        Param(arg.arg, default is None, True)
        for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True)
    ]
    return params, args.vararg is not None or args.kwarg is not None


def _call_args(fn: _Function, extra: set[str], *, last: bool) -> str:
    """Placeholders for the arguments of a call to *fn*.

    Required parameters appear by name (``name=...`` when keyword-only), plus the
    optional ones in *extra*. When *last* is set and others remain, ``...`` marks
    them.
    """
    params, variadic = _params(fn)
    shown: list[str] = []
    hidden = variadic
    for param in params:
        if param.required or param.name in extra:
            shown.append(f"{param.name}=..." if param.keyword_only else param.name)
        else:
            hidden = True
    if last and hidden:
        shown.append("...")
    return ", ".join(shown)


def _annotation(fn: _Function) -> ast.expr | None:
    node = fn.returns
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return ast.parse(node.value, mode="eval").body
    return node


def _union(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return [*_union(node.left), *_union(node.right)]
    return [node]


def _names_in(node: ast.AST) -> list[str]:
    return [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]


# --- The extractor ---------------------------------------------------------


class Extractor:
    def __init__(self, sources: Mapping[str, str]) -> None:
        """*sources* maps a module key (``_client``, ``resources/users``, ...) to
        its text."""
        self.classes: dict[str, ClassInfo] = {}
        self.consts: dict[str, dict[str, str]] = {}
        self.functions: dict[str, dict[str, _Function]] = {}
        self.delegated: set[str] = set()
        for module in sorted(sources):
            tree = ast.parse(sources[module], filename=module)
            self.consts[module] = {}
            self.functions[module] = {}
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    self._add_class(module, node)
                elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    self.functions[module][node.name] = node
                elif (
                    isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    self.consts[module][node.targets[0].id] = node.value.value

    def _add_class(self, module: str, node: ast.ClassDef) -> None:
        if node.name in self.classes:
            other = self.classes[node.name].module
            raise ExtractionError(
                f"class {node.name} is defined in both {other} and {module}; "
                "the extractor identifies classes by name"
            )
        info = ClassInfo(node.name, module, node)
        for base in node.bases:
            if isinstance(base, ast.Subscript) and isinstance(base.value, ast.Name):
                info.bases.append(base.value.id)
                if base.value.id == LAZY_BASE and isinstance(base.slice, ast.Name):
                    info.model = base.slice.id
            elif isinstance(base, ast.Name):
                info.bases.append(base.id)
        for item in node.body:
            if not isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            decorators = _decorator_names(item)
            if "overload" in decorators:
                continue  # the implementation carries the behaviour
            info.methods[item.name] = item
            if decorators & {"property", "cached_property"}:
                info.properties.add(item.name)
        self.classes[node.name] = info

    # -- lookups

    def _lineage(self, cls: ClassInfo) -> list[ClassInfo]:
        order = [cls]
        for base in cls.bases:
            if base in self.classes:
                order.extend(self._lineage(self.classes[base]))
        return order

    def _find_method(
        self, cls: ClassInfo, name: str, *, skip_lazy_base: bool = False
    ) -> tuple[ClassInfo, _Function] | None:
        for owner in self._lineage(cls):
            if skip_lazy_base and owner.name == LAZY_BASE:
                continue
            if name in owner.methods:
                return owner, owner.methods[name]
        return None

    def lazy_model(self, name: str) -> str | None:
        cls = self.classes.get(name)
        if cls is None:
            return None
        for owner in self._lineage(cls):
            if owner.model is not None:
                return owner.model
        return None

    def _where(self, ctx: Ctx, node: ast.AST) -> str:
        return f"{ctx.module}:{getattr(node, 'lineno', '?')}"

    # -- evaluation

    def _run(
        self,
        cls: ClassInfo | None,
        module: str,
        fn: _Function,
        bound: dict[str, Values],
        depth: int,
    ) -> Outcome:
        if depth > 8:
            raise ExtractionError(
                f"{module}: helper calls nest too deeply in {fn.name}"
            )
        params, _ = _params(fn)
        env: dict[str, Values] = {
            p.name: bound.get(p.name, frozenset({"{" + p.name + "}"})) for p in params
        }
        out = Outcome()
        self._block(fn.body, env, Ctx(cls, module, depth), out)
        return out

    def _block(
        self, statements: list[ast.stmt], env: dict[str, Values], ctx: Ctx, out: Outcome
    ) -> None:
        for statement in statements:
            self._statement(statement, env, ctx, out)

    def _statement(
        self, node: ast.stmt, env: dict[str, Values], ctx: Ctx, out: Outcome
    ) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            return
        if isinstance(node, ast.If):
            self._expression(node.test, env, ctx, out)
            taken, skipped = dict(env), dict(env)
            self._block(node.body, taken, ctx, out)
            self._block(node.orelse, skipped, ctx, out)
            env.clear()
            env.update(
                {k: taken[k] | skipped[k] for k in taken.keys() & skipped.keys()}
            )
            return
        if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
            self._expression(node.value, env, ctx, out)
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            values = self._render(node.value, env, ctx)
            for target in targets:
                if isinstance(target, ast.Name) and values is not None:
                    env[target.id] = values
                else:
                    for name in _names_in(target):
                        env.pop(name, None)
            return
        if isinstance(node, ast.AugAssign):
            self._expression(node.value, env, ctx, out)
            for name in _names_in(node.target):
                env.pop(name, None)
            return
        if isinstance(node, ast.Return):
            if node.value is not None:
                self._expression(node.value, env, ctx, out)
                values = self._render(node.value, env, ctx)
                if values is not None:
                    out.returns |= values
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                self._statement(child, env, ctx, out)
            elif isinstance(child, ast.ExceptHandler):
                self._block(child.body, env, ctx, out)
            elif isinstance(child, ast.withitem):
                self._expression(child.context_expr, env, ctx, out)
            else:
                self._expression(child, env, ctx, out)

    def _expression(
        self, node: ast.AST, env: dict[str, Values], ctx: Ctx, out: Outcome
    ) -> None:
        if isinstance(node, ast.Lambda):
            return
        if isinstance(node, ast.Call):
            self._call(node, env, ctx, out)
        for child in ast.iter_child_nodes(node):
            self._expression(child, env, ctx, out)

    def _call(
        self, call: ast.Call, env: dict[str, Values], ctx: Ctx, out: Outcome
    ) -> None:
        func = call.func
        name = _self_method(func)
        if name is not None:
            if name in PRIMITIVES:
                self._emit(
                    out, ctx, call, PRIMITIVES[name], _argument(call, 0, "path"), env
                )
                return
            if name == "_request":
                verb = self._verb(_argument(call, 0, "method"), ctx, call)
                self._emit(out, ctx, call, verb, _argument(call, 1, "path"), env)
                return
            found = self._find_method(ctx.cls, name) if ctx.cls else None
            if found is not None:
                owner, fn = found
                sub = self._invoke(ctx.cls, owner, fn, call, env, ctx)
                out.requests |= sub.requests
            return
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "_send"
            and isinstance(func.value, ast.Attribute)
            and _is_self(func.value.value)
            and func.value.attr == "_client"
        ):
            verb = self._verb(_argument(call, 0, "method"), ctx, call)
            url = _argument(call, 1, "url")
            if (
                isinstance(url, ast.Call)
                and isinstance(url.func, ast.Attribute)
                and url.func.attr == "_build_url"
                and url.args
            ):
                url = url.args[0]
            self._emit(out, ctx, call, verb, url, env)
            return
        if _is_super_init(func):
            if ctx.cls is not None and self.lazy_model(ctx.cls.name) is not None:
                self._emit(out, ctx, call, "GET", _argument(call, 1, "path"), env)
            return
        if isinstance(func, ast.Name):
            if func.id == "_send" and ctx.cls is None:
                verb = self._verb(_argument(call, 0, "method"), ctx, call)
                self._emit(out, ctx, call, verb, _argument(call, 1, "url"), env)
            elif func.id == PAGE_CLASS:
                self._emit(out, ctx, call, "GET", _argument(call, 1, "path"), env)
            elif func.id in self.classes:
                self._construct(self.classes[func.id], call, env, ctx, out)
            return
        if (
            isinstance(func, ast.Call)
            and isinstance(func.func, ast.Name)
            and func.func.id in self.classes
        ):
            # ``Resource(self)(...)``: the callable's own body does the request.
            cls = self.classes[func.func.id]
            found = self._find_method(cls, "__call__")
            if found is not None:
                self.delegated.add(cls.name)
                owner, fn = found
                sub = self._invoke(cls, owner, fn, call, env, ctx)
                out.requests |= sub.requests

    def _construct(
        self,
        cls: ClassInfo,
        call: ast.Call,
        env: dict[str, Values],
        ctx: Ctx,
        out: Outcome,
    ) -> None:
        lazy = self.lazy_model(cls.name) is not None
        found = self._find_method(cls, "__init__", skip_lazy_base=True)
        if found is None:
            if lazy:
                self._emit(
                    out, ctx, call, "GET", _argument(call, 1, "path"), env, via=cls.name
                )
            return
        owner, fn = found
        sub = self._invoke(cls, owner, fn, call, env, ctx)
        for request in sub.requests:
            via = cls.name if lazy else request.via
            out.requests.add(Request(request.verb, request.route, via))

    def _invoke(
        self,
        receiver: ClassInfo | None,
        owner: ClassInfo,
        fn: _Function,
        call: ast.Call,
        env: dict[str, Values],
        ctx: Ctx,
    ) -> Outcome:
        """Evaluate *fn* with the arguments of *call* bound to its parameters."""
        params, _ = _params(fn)
        positional = [p.name for p in params if not p.keyword_only]
        bound: dict[str, Values] = {}
        for name, arg in zip(positional, call.args, strict=False):
            if isinstance(arg, ast.Starred):
                break
            values = self._render(arg, env, ctx)
            if values is not None:
                bound[name] = values
        known = {p.name for p in params}
        for keyword in call.keywords:
            if keyword.arg in known:
                values = self._render(keyword.value, env, ctx)
                if values is not None:
                    bound[keyword.arg] = values
        return self._run(receiver, owner.module, fn, bound, ctx.depth + 1)

    def _verb(self, node: ast.expr | None, ctx: Ctx, call: ast.Call) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value.upper()
        raise ExtractionError(
            f"{self._where(ctx, call)}: the HTTP method is not a literal"
        )

    def _emit(
        self,
        out: Outcome,
        ctx: Ctx,
        call: ast.Call,
        verb: str,
        path: ast.expr | None,
        env: dict[str, Values],
        *,
        via: str | None = None,
    ) -> None:
        routes = self._render(path, env, ctx) if path is not None else None
        if routes is None:
            raise ExtractionError(
                f"{self._where(ctx, call)}: cannot resolve the request path"
            )
        for route in routes:
            out.requests.add(Request(verb, route, via))

    def _render(
        self, node: ast.expr | None, env: dict[str, Values], ctx: Ctx
    ) -> Values | None:
        """The string values *node* can take, with ``{name}`` for each parameter."""
        if isinstance(node, ast.Constant):
            return frozenset({node.value}) if isinstance(node.value, str) else None
        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            const = self.consts.get(ctx.module, {}).get(node.id)
            return frozenset({const}) if const is not None else None
        if isinstance(node, ast.Attribute):
            if _is_self(node.value):
                name = node.attr.lstrip("_")
                return frozenset({"{" + ATTRIBUTE_MARK + name + "}"})
            return None
        if isinstance(node, ast.JoinedStr):
            parts: list[Values] = []
            for piece in node.values:
                if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                    parts.append(frozenset({piece.value}))
                elif isinstance(piece, ast.FormattedValue):
                    rendered = self._render(piece.value, env, ctx)
                    parts.append(
                        rendered if rendered is not None else frozenset({"{}"})
                    )
            return frozenset("".join(combo) for combo in itertools.product(*parts))
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "path_segment":
                if node.args:
                    return self._render(node.args[0], env, ctx) or frozenset({"{}"})
                return None
            name = _self_method(node.func)
            if name is not None and name not in PRIMITIVES and ctx.cls is not None:
                found = self._find_method(ctx.cls, name)
                if found is not None:
                    owner, fn = found
                    sub = self._invoke(ctx.cls, owner, fn, node, env, ctx)
                    return frozenset(sub.returns) or None
        return None

    # -- classification

    def _type_text(self, node: ast.expr, where: str) -> str:
        """A return annotation in sync spelling; a lazy proxy shows its model."""
        if isinstance(node, ast.Constant):
            if node.value is None:
                return "None"
            raise ExtractionError(f"{where}: unsupported return annotation")
        if isinstance(node, ast.Name):
            model = self.lazy_model(node.id)
            if model is not None:
                return f"{model} (lazy)"
            if node.id in SYNC_TYPE_NAMES:
                return SYNC_TYPE_NAMES[node.id]
            if node.id.startswith("Async"):
                raise ExtractionError(
                    f"{where}: return type {node.id} has no sync name in SYNC_TYPE_NAMES"
                )
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr if _names_in(node) == ["builtins"] else ast.unparse(node)
        if isinstance(node, ast.Subscript):
            inner = node.slice
            items = inner.elts if isinstance(inner, ast.Tuple) else [inner]
            args = ", ".join(self._type_text(i, where) for i in items)
            return f"{self._type_text(node.value, where)}[{args}]"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return " | ".join(self._type_text(m, where) for m in _union(node))
        raise ExtractionError(f"{where}: unsupported return annotation")

    def _returns(self, fn: _Function, request: Request, where: str) -> tuple[str, bool]:
        annotation = _annotation(fn)
        if annotation is None:
            raise ExtractionError(
                f"{where}: public operation without a return annotation"
            )
        members = _union(annotation)
        if request.via is not None:
            matching = [m for m in members if _names_in(m) == [request.via]]
            if not matching:
                raise ExtractionError(
                    f"{where}: constructs {request.via}, which the return "
                    "annotation does not name"
                )
            members = matching
        paginated = any(
            isinstance(m, ast.Subscript) and _names_in(m)[:1] == [PAGE_CLASS]
            for m in members
        )
        text = " | ".join(self._type_text(m, where) for m in members)
        return text, paginated

    def _targets(self, fn: _Function) -> list[str]:
        annotation = _annotation(fn)
        if annotation is None:
            return []
        return sorted(
            {n for n in _names_in(annotation) if n in self.classes and n != PAGE_CLASS}
        )

    def _client_classes(self) -> list[ClassInfo]:
        client = self.classes.get(CLIENT_CLASS)
        if client is None:
            raise ExtractionError(f"class {CLIENT_CLASS} not found")
        return [
            client,
            *(c for c in self.classes.values() if c.module.startswith("resources/")),
        ]

    def extract(self) -> list[Row]:
        """Every operation row of the client, sorted."""
        edges: dict[str, list[Edge]] = {}
        operations: dict[str, list[tuple[str, _Function, Request]]] = {}
        for cls in self._client_classes():
            edges[cls.name] = []
            operations[cls.name] = []
            for name, fn in cls.methods.items():
                if name.startswith("_") and name != "__call__":
                    continue
                where = f"{cls.module}:{fn.lineno} {cls.name}.{name}"
                targets = self._targets(fn)
                if name in cls.properties:
                    if not targets:
                        raise ExtractionError(
                            f"{where}: property returns no SDK class, so no chain can follow it"
                        )
                    edges[cls.name] += [Edge(f".{name}", t) for t in targets]
                    continue
                outcome = self._run(cls, cls.module, fn, {}, 0)
                lazy = [t for t in targets if self.lazy_model(t) is not None]
                plain = [t for t in targets if t not in lazy]
                if outcome.requests:
                    if plain:
                        raise ExtractionError(
                            f"{where}: sends a request and returns {plain[0]}, "
                            "which is not a lazy proxy"
                        )
                    operations[cls.name] += [
                        (name, fn, request)
                        for request in sorted(
                            outcome.requests, key=lambda r: (r.route, r.verb)
                        )
                    ]
                elif lazy:
                    raise ExtractionError(
                        f"{where}: returns a lazy proxy but no request was found"
                    )
                elif not targets and (cls.name, name) not in NON_OPERATIONS:
                    raise ExtractionError(
                        f"{where}: public method sends no request and leads to no SDK "
                        "class; teach the extractor this request pattern or add it to "
                        "NON_OPERATIONS"
                    )
                if targets:
                    args = _call_args(fn, set(), last=False)
                    edges[cls.name] += [Edge(f".{name}({args})", t) for t in targets]
        unknown = {
            (c, m) for c, m in NON_OPERATIONS if m not in self.classes[c].methods
        }
        if unknown:
            raise ExtractionError(
                f"NON_OPERATIONS names no such method: {sorted(unknown)}"
            )

        chains: dict[str, list[str]] = {}

        def walk(cls_name: str, chain: str, stack: tuple[str, ...]) -> None:
            chains.setdefault(cls_name, []).append(chain)
            for edge in sorted(edges.get(cls_name, []), key=lambda e: e.text):
                if edge.target in stack:
                    raise ExtractionError(f"{edge.target} is reachable from itself")
                walk(edge.target, chain + edge.text, (*stack, edge.target))

        walk(CLIENT_CLASS, "client", (CLIENT_CLASS,))
        for cls in self._client_classes():
            if cls.name not in chains and cls.name not in self.delegated:
                raise ExtractionError(
                    f"{cls.module}: class {cls.name} is not reachable from "
                    f"{CLIENT_CLASS}: expose it through a property or an accessor "
                    "method"
                )

        rows: set[Row] = set()
        for cls_name, chain_list in chains.items():
            cls = self.classes[cls_name]
            for name, fn, request in operations.get(cls_name, []):
                where = f"{cls.module}:{fn.lineno} {cls.name}.{name}"
                returns, paginated = self._returns(fn, request, where)
                shown = set(re.findall(r"\{(\w+)\}", request.route))
                route = request.route.replace(ATTRIBUTE_MARK, "")
                for chain in chain_list:
                    args = _call_args(fn, shown, last=True)
                    call = (
                        f"{chain}({args})"
                        if name == "__call__"
                        else f"{chain}.{name}({args})"
                    )
                    rows.add(Row(request.verb, route, call, returns, paginated))
        return sorted(rows, key=_row_key)

    def extract_oauth(self, exported: set[str] | None) -> list[Row]:
        """Rows for the public module-level functions of the OAuth module."""
        rows: set[Row] = set()
        for name, fn in self.functions.get(OAUTH_MODULE, {}).items():
            if name.startswith("_"):
                continue
            where = f"{OAUTH_MODULE}:{fn.lineno} {name}"
            if exported is not None and not {name, f"async_{name}"} <= exported:
                raise ExtractionError(
                    f"{where}: discogs_sdk.oauth does not export {name} and async_{name}"
                )
            outcome = self._run(None, OAUTH_MODULE, fn, {}, 0)
            if not outcome.requests:
                raise ExtractionError(f"{where}: public function sends no request")
            for request in outcome.requests:
                if not request.route.startswith("{}/"):
                    raise ExtractionError(
                        f"{where}: expected a path below the base URL, got {request.route}"
                    )
                route = request.route[2:].replace(ATTRIBUTE_MARK, "")
                returns, _ = self._returns(fn, request, where)
                call = f"discogs_sdk.oauth.{name}({_call_args(fn, set(), last=True)})"
                rows.add(Row(request.verb, route, call, returns, False))
        return sorted(rows, key=_row_key)


def _row_key(row: Row) -> tuple[str, int, str]:
    return row.route, VERB_ORDER.get(row.verb, len(VERB_ORDER)), row.call


# --- Loading and rendering -------------------------------------------------


def load_sources(directory: Path = ASYNC_SRC) -> dict[str, str]:
    return {
        path.relative_to(directory).with_suffix("").as_posix(): path.read_text()
        for path in sorted(directory.rglob("*.py"))
    }


def _oauth_exports() -> set[str]:
    for node in ast.parse(OAUTH_PUBLIC.read_text()).body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__all__"
        ):
            return set(ast.literal_eval(node.value))
    raise ExtractionError(f"{OAUTH_PUBLIC.name} has no __all__")


def build_map(
    sources: Mapping[str, str] | None = None, exported: set[str] | None = None
) -> EndpointMap:
    """Extract the endpoint map from *sources* (the SDK's by default)."""
    if sources is None:
        sources = load_sources()
        exported = _oauth_exports()
    extractor = Extractor(sources)
    return EndpointMap(extractor.extract(), extractor.extract_oauth(exported))


def sdk_routes() -> set[str]:
    """Every route the SDK sends, as ``{}``-normalised templates."""
    return build_map().routes()


_INTRO = """\
# Endpoint map

<!-- Generated by scripts/generate_endpoints.py from the SDK sources; do not edit.
     Run `just generate-endpoints` after changing a resource. -->

Which SDK call reaches which Discogs endpoint. Look up the route you know from the
Discogs API reference and read off the call, or look up a call and see what it sends.

## Reading the tables

- **Calls** use the sync client (`client = Discogs(...)`). `AsyncDiscogs` has the same
  chain: `await` an operation, `await` a lazy result to load it, and iterate a page with
  `async for`. See [Getting started](getting-started.md) and [Pagination](pagination.md).
- **Arguments** carry the parameter names from the method signature. Required ones are
  shown, as `name=...` when keyword-only, and so are the optional ones that change the
  route. A trailing `...` stands for the other optional arguments, so `list(...)` can
  also take `page` and `per_page`.
- **Several rows for one call** mean its route depends on its arguments: the same call
  with and without an optional argument reaches two routes.
- **Returns** is the type the call evaluates to. `Release (lazy)` is a proxy that
  sends nothing until you read a field (sync) or await it (async); it resolves to a
  `Release`. A call that returns `SyncPage[...]` (`AsyncPage[...]` with the async client)
  is paginated.
- **Verb and route** are what the call sends. `{name}` is a path parameter. One route can
  appear under several verbs, each with its own call.
- Each `.get(...)` that returns a lazy proxy also continues the chain: its sub-resources
  (`.rating`, `.collection`) send nothing until you call an operation on them.

## Client operations

| Verb | Route | Call | Returns | Paginated |
|---|---|---|---|---|
"""

_OAUTH = """
## OAuth token exchange

The token-exchange routes are not client operations: they run before there is an
authorized client, so they are module-level functions of `discogs_sdk.oauth` with no
`client.` chain. Each has an async twin named `async_<name>`. See
[Authentication](authentication.md).

| Verb | Route | Call | Returns |
|---|---|---|---|
"""


def _cell(text: str) -> str:
    return "`" + text.replace("|", "\\|") + "`"


def render_markdown(endpoint_map: EndpointMap) -> str:
    lines = [_INTRO.rstrip("\n")]
    for row in endpoint_map.operations:
        paginated = "yes" if row.paginated else "no"
        lines.append(
            f"| {row.verb} | {_cell(row.route)} | {_cell(row.call)} "
            f"| {_cell(row.returns)} | {paginated} |"
        )
    lines.append(_OAUTH.rstrip("\n"))
    for row in endpoint_map.oauth:
        lines.append(
            f"| {row.verb} | {_cell(row.route)} | {_cell(row.call)} "
            f"| {_cell(row.returns)} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check", action="store_true", help="fail when docs/endpoints.md is stale"
    )
    args = parser.parse_args()

    try:
        text = render_markdown(build_map())
    except ExtractionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    target = OUTPUT.relative_to(ROOT)
    if not args.check:
        OUTPUT.write_text(text)
        print(f"Wrote {target}.")
        return
    current = OUTPUT.read_text() if OUTPUT.exists() else ""
    if current == text:
        print(f"{target} is up to date.")
        return
    diff = difflib.unified_diff(
        current.splitlines(),
        text.splitlines(),
        fromfile=f"{target} (committed)",
        tofile=f"{target} (generated)",
        lineterm="",
    )
    print("\n".join(itertools.islice(diff, 60)), file=sys.stderr)
    print(
        f"ERROR: {target} is out of date with the SDK sources. "
        "Run `just generate-endpoints` and commit the result.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
