"""Compile-check every example file.

Verifies that:
  - Each example is valid Python (AST parses)
  - Its import statements resolve (no renamed or deleted modules and names)
  - It imports the SDK only through public names, never a ``_``-prefixed module

Nothing here runs an example or touches the API: a call that no longer exists,
a wrong argument or a broken request order all pass this check.
tests/test_examples_behavior.py runs the examples that write to the API
(collection, marketplace, database, advanced) under mocked HTTP and pins every
request they send. The others (quickstart, async_usage, and authentication,
which prompts for input) are not run anywhere.
"""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

import pytest

from tests.conftest import EXAMPLES_DIR

EXAMPLE_FILES = sorted(EXAMPLES_DIR.glob("*.py"))


def _extract_imports(source: str) -> str:
    """Return source containing only import statements from *source*."""
    tree = ast.parse(source)
    import_lines: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            segment = ast.get_source_segment(source, node)
            if segment is not None:
                import_lines.append(segment)
    return "\n".join(import_lines)


@pytest.mark.parametrize(
    "example_path",
    EXAMPLE_FILES,
    ids=[p.stem for p in EXAMPLE_FILES],
)
def test_example_imports(example_path: Path):
    """All imports in the example must resolve."""
    source = example_path.read_text()

    # Phase 1: AST parses (valid syntax).
    ast.parse(source)

    # Phase 2: imports resolve.
    import_source = _extract_imports(source)
    module_name = f"_example_imports_.{example_path.stem}"
    module = types.ModuleType(module_name)
    module.__file__ = str(example_path)
    sys.modules[module_name] = module
    try:
        exec(compile(import_source, example_path, "exec"), module.__dict__)  # noqa: S102
    finally:
        sys.modules.pop(module_name, None)


def _private_sdk_imports(source: str) -> list[str]:
    """Return every import in *source* that reaches a private ``discogs_sdk`` path."""
    private: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            paths = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            # ``from discogs_sdk import _cache`` names a private module too.
            paths = [f"{node.module}.{alias.name}" for alias in node.names]
        else:
            continue
        for path in paths:
            parts = path.split(".")
            if parts[0] == "discogs_sdk" and any(p.startswith("_") for p in parts):
                private.append(path)
    return private


@pytest.mark.parametrize(
    "example_path",
    EXAMPLE_FILES,
    ids=[p.stem for p in EXAMPLE_FILES],
)
def test_example_imports_only_public_sdk_names(example_path: Path):
    """Examples teach usage, so a private path there becomes a user's dependency."""
    assert _private_sdk_imports(example_path.read_text()) == []


@pytest.mark.parametrize(
    "source",
    [
        "from discogs_sdk._cache import ResponseCache",
        "from discogs_sdk import _cache",
        "import discogs_sdk._cache",
        "from discogs_sdk.models._timestamp import Timestamp",
    ],
)
def test_private_import_detection(source: str):
    assert _private_sdk_imports(source) != []


@pytest.mark.parametrize(
    "example_path",
    EXAMPLE_FILES,
    ids=[p.stem for p in EXAMPLE_FILES],
)
def test_example_cache_dir_is_not_in_tmp(example_path: Path):
    """A predictable path under /tmp lets other local users read or plant the cache."""
    for node in ast.walk(ast.parse(example_path.read_text())):
        if isinstance(node, ast.keyword) and node.arg == "cache_dir":
            assert "/tmp" not in ast.unparse(node.value)
