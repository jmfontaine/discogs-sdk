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


class AsyncToSyncTransformer(ast.NodeTransformer):
    """Convert async Python AST to sync Python AST."""

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
    """Regenerate into a temp dir and compare against the existing _sync/."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dst = Path(tmp) / "_sync"
        count = _generate(tmp_dst)
        _ruff_format(tmp_dst)

        if not DST.exists():
            print(f"ERROR: {DST.relative_to(ROOT)} does not exist. Run: python scripts/generate_sync.py")
            sys.exit(1)

        cmp = filecmp.dircmp(str(tmp_dst), str(DST))
        stale = _find_differences(cmp)

        if stale:
            print("ERROR: _sync/ is out of date. Run: python scripts/generate_sync.py")
            for path in sorted(stale):
                print(f"  {path}")
            sys.exit(1)

        print(f"OK: _sync/ is up to date ({count} files)")


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
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ruff format failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)


def transform(source: str) -> str:
    """Transform async source code to sync using AST."""
    tree = ast_comments.parse(source)
    transformer = AsyncToSyncTransformer()
    tree = transformer.visit(tree)
    ast.fix_missing_locations(tree)
    result = ast_comments.unparse(tree)
    return HEADER + "\n" + result + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sync client from async source.")
    parser.add_argument("--check", action="store_true", help="Check that _sync/ is up to date (no writes)")
    args = parser.parse_args()

    if args.check:
        _check()
        return

    count = _generate(DST)
    for src_file in sorted(SRC.rglob("*.py")):
        print(f"  {src_file.relative_to(SRC)}")

    print(f"\nGenerated {count} files in {DST.relative_to(ROOT)}")

    print("\nRunning ruff format...")
    _ruff_format(DST)
    print("Done.")


if __name__ == "__main__":
    main()
