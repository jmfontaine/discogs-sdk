#!/usr/bin/env python3
"""Generate sync client code from the async source of truth.

Usage:
    python scripts/generate_sync.py

The async code under src/discogs_sdk/_async/ is the single source of truth.
This script uses an AST-based transformer to produce the sync equivalent
under src/discogs_sdk/_sync/.

Branch directives:
    if True:  # ASYNC          — with else: splice in the else body only
    if True:  # ASYNC          — without else: remove entirely
"""

from __future__ import annotations

import argparse
import ast
import copy
import filecmp
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import ast_comments

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "discogs_sdk" / "_async"
DST = ROOT / "src" / "discogs_sdk" / "_sync"

HEADER = "# This file is auto-generated from the async version.\n# Do not edit directly — edit the corresponding file in _async/ instead.\n"

NAME_MAP: dict[str, str] = {
    "__aenter__": "__enter__",
    "__aexit__": "__exit__",
    "__aiter__": "__iter__",
    "__anext__": "__next__",
    "aclose": "close",
    "AsyncAPIResource": "SyncAPIResource",
    "AsyncCacheClient": "SyncCacheClient",
    "AsyncSqliteStorage": "SyncSqliteStorage",
    "AsyncClient": "Client",
    "asynccontextmanager": "contextmanager",
    "AsyncDiscogs": "Discogs",
    "AsyncIterator": "Iterator",
    "AsyncLazyResource": "LazyResource",
    "AsyncPage": "SyncPage",
    "StopAsyncIteration": "StopIteration",
}

MODELS = ROOT / "src" / "discogs_sdk" / "models"
FIELDS_MODULE = MODELS / "_lazy_fields.py"
FIELDS_IMPORT = "discogs_sdk.models._lazy_fields"

FIELDS_HEADER = '''# This file is auto-generated from the model definitions.
# Do not edit directly — edit the models in discogs_sdk/models/ instead.
"""Declared members of every model reachable through a lazy proxy.

A sync proxy resolves on attribute access, so consumers read model members
straight off the proxy. These mixins declare those members — and only those —
so a misspelled name is a static error rather than a dynamic ``Any``.

Everything is declared under ``TYPE_CHECKING``: at runtime the classes are
empty, which leaves the proxy's ``__getattr__`` free to resolve and delegate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
'''


def _is_async_branch(node: ast.If) -> bool:
    """Return True if ``node`` is ``if True:  # ASYNC``."""
    if not (isinstance(node.test, ast.Constant) and node.test.value is True):
        return False
    # ast_comments inserts Comment nodes with inline=True for trailing comments.
    # The ``# ASYNC`` comment ends up as the first item in the body.
    if node.body and isinstance(node.body[0], ast_comments.Comment):
        return "ASYNC" in node.body[0].value
    return False


def _rename_in_string(s: str) -> str:
    """Apply NAME_MAP replacements inside a string value."""
    for old, new in NAME_MAP.items():
        s = s.replace(old, new)
    return s


def _lazy_model_of(node: ast.ClassDef) -> str | None:
    """Return the model name ``M`` if *node* subclasses ``AsyncLazyResource[M]``."""
    for base in node.bases:
        if (
            isinstance(base, ast.Subscript)
            and isinstance(base.value, ast.Name)
            and base.value.id in ("AsyncLazyResource", "LazyResource")
            and isinstance(base.slice, ast.Name)
        ):
            return base.slice.id
    return None


def _proxied_models() -> list[str]:
    """Every model a lazy proxy resolves to, read from the async source."""
    found: set[str] = set()
    for src_file in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(src_file.read_text())):
            if isinstance(node, ast.ClassDef) and (model := _lazy_model_of(node)):
                found.add(model)
    return sorted(found)


def _model_declarations() -> tuple[dict[str, list[str]], dict[str, str]]:
    """Return each model's declared members and a symbol -> module index.

    Members are rendered from the model source, so the model definition stays the
    single source of truth: annotated fields keep their annotation, and properties
    and dunder methods keep their signature with an elided body.
    """
    members: dict[str, list[str]] = {}
    symbols: dict[str, str] = {}
    for model_file in sorted(MODELS.glob("*.py")):
        if model_file == FIELDS_MODULE:
            continue
        module = f"discogs_sdk.models.{model_file.stem}"
        for node in ast.parse(model_file.read_text()).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        symbols[target.id] = module
                continue
            if not isinstance(node, ast.ClassDef):
                continue
            symbols[node.name] = module
            rendered: list[str] = []
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    rendered.append(f"{stmt.target.id}: {ast.unparse(stmt.annotation)}")
                elif isinstance(stmt, ast.FunctionDef):
                    stub = copy.deepcopy(stmt)
                    stub.body = [ast.Expr(value=ast.Constant(value=...))]
                    rendered.append(ast.unparse(stub))
            members[node.name] = rendered
    return members, symbols


def _render_field_mixins() -> str:
    """Render the member-declaration module from the model definitions."""
    members, symbols = _model_declarations()
    blocks: list[str] = []
    needed: set[str] = set()
    for model in _proxied_models():
        if model not in members:
            print(f"ERROR: no model named {model} in {MODELS.relative_to(ROOT)}", file=sys.stderr)
            sys.exit(1)
        declarations = members[model]
        body = "\n".join(f"        {line}" for decl in declarations for line in decl.splitlines()) or "        pass"
        for decl in declarations:
            needed.update(name.id for name in ast.walk(ast.parse(decl)) if isinstance(name, ast.Name))
        blocks.append(
            f'class {model}Fields:\n    """Members of :class:`{model}`."""\n\n    if TYPE_CHECKING:\n{body}\n'
        )

    imports = sorted({(symbols[name], name) for name in needed if name in symbols})
    import_block = "\n".join(f"    from {module} import {name}" for module, name in imports)
    header = FIELDS_HEADER
    if import_block:
        header += f"\nif TYPE_CHECKING:\n{import_block}\n"
    return header + "\n\n" + "\n\n".join(blocks)


class AsyncToSyncTransformer(ast.NodeTransformer):
    """Convert async Python AST to sync Python AST."""

    def __init__(self) -> None:
        # Models whose field declarations the generated module must import.
        self.field_mixins: list[str] = []

    def visit_AsyncFor(self, node: ast.AsyncFor) -> ast.For:
        self.generic_visit(node)
        new_node = ast.For(
            target=node.target,
            iter=node.iter,
            body=node.body,
            orelse=node.orelse,
            type_comment=getattr(node, "type_comment", None),
        )
        return ast.copy_location(new_node, node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        new_name = NAME_MAP.get(node.name, node.name)
        new_node = ast.FunctionDef(
            name=new_name,
            args=node.args,
            body=node.body,
            decorator_list=node.decorator_list,
            returns=node.returns,
            type_comment=getattr(node, "type_comment", None),
        )
        return ast.copy_location(new_node, node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> ast.With:
        self.generic_visit(node)
        new_node = ast.With(
            items=node.items,
            body=node.body,
            type_comment=getattr(node, "type_comment", None),
        )
        return ast.copy_location(new_node, node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.Attribute:
        self.generic_visit(node)
        new_attr = NAME_MAP.get(node.attr, node.attr)
        if new_attr != node.attr:
            node.attr = new_attr
        return node

    def visit_Await(self, node: ast.Await) -> ast.AST:
        self.generic_visit(node)
        return node.value

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        self.generic_visit(node)
        new_name = NAME_MAP.get(node.name, node.name)
        if new_name != node.name:
            node.name = new_name
        # A sync proxy resolves on attribute access, so it exposes the model's
        # fields directly. Mix in their declarations; the async proxy must not,
        # because its data is only reachable after an explicit await.
        if model := _lazy_model_of(node):
            mixin = f"{model}Fields"
            node.bases.append(ast.Name(id=mixin, ctx=ast.Load()))
            self.field_mixins.append(mixin)
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        if isinstance(node.value, str):
            new_value = _rename_in_string(node.value)
            if new_value != node.value:
                node.value = new_value
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        new_name = NAME_MAP.get(node.name, node.name)
        if new_name != node.name:
            node.name = new_name
        return node

    def visit_If(self, node: ast.If) -> ast.AST | list[ast.AST]:
        if _is_async_branch(node):
            if node.orelse:
                # Splice in the else body, visiting each node recursively.
                result = []
                for child in node.orelse:
                    visited = self.visit(child)
                    if isinstance(visited, list):
                        result.extend(visited)
                    elif visited is not None:
                        result.append(visited)
                return result
            else:
                # No else branch: remove entirely.
                return []

        # Normal if statement — visit children as usual.
        self.generic_visit(node)
        return node

    def visit_Import(self, node: ast.Import) -> ast.Import:
        for alias in node.names:
            alias.name = NAME_MAP.get(alias.name, alias.name)
            if alias.asname:
                alias.asname = NAME_MAP.get(alias.asname, alias.asname)
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:
        if node.module:
            node.module = node.module.replace("discogs_sdk._async", "discogs_sdk._sync")
        for alias in node.names:
            alias.name = NAME_MAP.get(alias.name, alias.name)
            if alias.asname:
                alias.asname = NAME_MAP.get(alias.asname, alias.asname)
        return node

    def visit_Name(self, node: ast.Name) -> ast.Name:
        new_id = NAME_MAP.get(node.id, node.id)
        if new_id != node.id:
            node.id = new_id
        return node


def _check() -> None:
    """Regenerate into a temp dir and compare against the existing generated files."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dst = Path(tmp) / "_sync"
        count = _generate(tmp_dst)
        tmp_fields = Path(tmp) / "_lazy_fields.py"
        tmp_fields.write_text(_render_field_mixins())
        _ruff_format(tmp_dst)
        _ruff_format(tmp_fields)

        if not DST.exists():
            print(f"ERROR: {DST.relative_to(ROOT)} does not exist. Run: python scripts/generate_sync.py")
            sys.exit(1)

        stale = _find_differences(filecmp.dircmp(str(tmp_dst), str(DST)))
        if not FIELDS_MODULE.exists() or FIELDS_MODULE.read_text() != tmp_fields.read_text():
            stale.append(str(FIELDS_MODULE.relative_to(ROOT)))

        if stale:
            print("ERROR: generated code is out of date. Run: python scripts/generate_sync.py")
            for path in sorted(stale):
                print(f"  {path}")
            sys.exit(1)

        print(f"OK: generated code is up to date ({count + 1} files)")


def _find_differences(cmp: filecmp.dircmp[str], prefix: str = "") -> list[str]:
    """Recursively collect differing/missing file paths."""
    diffs: list[str] = []
    for name in cmp.left_only:
        diffs.append(f"{prefix}{name} (missing in _sync/)")
    for name in cmp.right_only:
        diffs.append(f"{prefix}{name} (extra in _sync/)")
    for name in cmp.diff_files:
        diffs.append(f"{prefix}{name}")
    for sub_dir, sub_cmp in cmp.subdirs.items():
        diffs.extend(_find_differences(sub_cmp, prefix=f"{sub_dir}/"))
    return diffs


def _generate(dst: Path) -> int:
    """Generate sync files into *dst*. Return file count."""
    if dst.exists():
        shutil.rmtree(dst)

    count = 0
    for src_file in sorted(SRC.rglob("*.py")):
        rel = src_file.relative_to(SRC)
        dst_file = dst / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)

        content = src_file.read_text()
        dst_file.write_text(transform(content))
        count += 1

    return count


def _ruff_format(target: Path) -> None:
    # `format` runs first: ast_comments.unparse emits f-strings that reuse the outer
    # quote (3.12+ syntax only), and formatting normalizes them. `check` then sorts the
    # single unseparated import block unparse produces (I001), and `format` runs again
    # to tidy what the import fixes moved.
    for args, label in (
        (["format"], "ruff format"),
        (["check", "--select", "I", "--fix", "--quiet"], "ruff check"),
        (["format"], "ruff format"),
    ):
        result = subprocess.run(
            [sys.executable, "-m", "ruff", *args, str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"{label} failed:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)


def _import_insertion_point(body: list[ast.stmt]) -> int:
    """First index that may hold a regular import.

    ``from __future__`` statements must stay ahead of every other statement, and
    a module docstring ahead of those, so skip past both.
    """
    index = 0
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        index = 1
    while index < len(body):
        statement = body[index]
        if not (isinstance(statement, ast.ImportFrom) and statement.module == "__future__"):
            break
        index += 1
    return index


def transform(source: str) -> str:
    """Transform async source code to sync using AST."""
    tree = ast_comments.parse(source)
    transformer = AsyncToSyncTransformer()
    tree = transformer.visit(tree)
    if transformer.field_mixins:
        names = [ast.alias(name=mixin) for mixin in sorted(set(transformer.field_mixins))]
        import_node = ast.ImportFrom(module=FIELDS_IMPORT, names=names, level=0)
        tree.body.insert(_import_insertion_point(tree.body), import_node)
    ast.fix_missing_locations(tree)
    result = ast_comments.unparse(tree)
    return HEADER + "\n" + result + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sync client from async source.")
    parser.add_argument("--check", action="store_true", help="Check that generated code is up to date (no writes)")
    args = parser.parse_args()

    if args.check:
        _check()
        return

    FIELDS_MODULE.write_text(_render_field_mixins())
    count = _generate(DST)
    for src_file in sorted(SRC.rglob("*.py")):
        print(f"  {src_file.relative_to(SRC)}")

    print(f"\nGenerated {count} files in {DST.relative_to(ROOT)}")
    print(f"Generated {FIELDS_MODULE.relative_to(ROOT)}")

    print("\nRunning ruff format...")
    _ruff_format(DST)
    _ruff_format(FIELDS_MODULE)
    print("Done.")


if __name__ == "__main__":
    main()
