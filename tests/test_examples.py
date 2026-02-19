"""Compile-check every example file.

Verifies that:
  - Each example is valid Python (AST parses)
  - All imports resolve (no renamed/deleted classes or modules)

Examples are NOT executed — only import statements are run.
This catches the most common form of drift (API surface changes)
without requiring mocks or a live API.
"""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
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
