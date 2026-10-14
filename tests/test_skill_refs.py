"""The packaged agent skill and its references.

``scripts/generate_skill_refs.py --check`` keeps each reference equal to its
docs page. What it cannot see is a stray file outside ``references/``, or a
link in SKILL.md to a reference that is not generated.
"""

from __future__ import annotations

import importlib.util
from types import ModuleType

from tests.conftest import REPO_ROOT
from tests.markdown_links import find_links

SKILL_DIR = REPO_ROOT / "src" / "discogs_sdk" / ".agents" / "skills" / "discogs-sdk"


def _script(name: str) -> ModuleType:
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _skill_tree() -> set[str]:
    return {
        path.relative_to(SKILL_DIR).as_posix()
        for path in SKILL_DIR.rglob("*")
        if path.is_file()
    }


def test_every_skill_file_is_generated_or_skill_md():
    pages = _script("generate_skill_refs").PAGES
    assert _skill_tree() == {"SKILL.md", *(f"references/{page}" for page in pages)}


def test_skill_md_links_every_reference():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    linked = {
        link.target.partition("#")[0]
        for link in find_links(text)
        if link.target.startswith("references/")
    }
    assert linked == {name for name in _skill_tree() if name.startswith("references/")}
