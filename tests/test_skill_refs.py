"""The packaged agent skill and its references.

``scripts/generate_skill_refs.py --check`` keeps each reference equal to its
docs page. What it cannot see is a stray file outside ``references/``, or a
link in SKILL.md to a reference that is not generated.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

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


def test_check_tells_a_stale_reference_from_an_unexpected_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    # A one-page project, so the paths printed are relative to tmp_path.
    generator = _script("generate_skill_refs")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "1.0.0"\n', encoding="utf-8"
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\n", encoding="utf-8")
    references = tmp_path / "references"
    references.mkdir()
    (references / "guide.md").write_text("edited\n", encoding="utf-8")
    (references / "notes.md").write_text("notes\n", encoding="utf-8")
    monkeypatch.setattr(generator, "ROOT", tmp_path)
    monkeypatch.setattr(generator, "DOCS", docs)
    monkeypatch.setattr(generator, "PAGES", ("guide.md",))
    monkeypatch.setattr(generator, "REFERENCES", references)
    monkeypatch.setattr(sys, "argv", ["generate_skill_refs.py", "--check"])

    assert generator.main() == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "stale: references/guide.md" in err
    assert "unexpected: references/notes.md" in err
    assert "stale: references/notes.md" not in err
    assert "just generate-skill-refs" in err


@pytest.mark.parametrize(
    ("version", "ref"),
    [
        ("0.8.1", "v0.8.1"),
        ("0.9.0.dev0", "main"),
        ("0.9.0rc1", "main"),
    ],
)
def test_references_link_the_release_tag_only_for_a_release_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str, ref: str
):
    # A development or pre-release version is never tagged, so its links name main.
    generator = _script("generate_skill_refs")
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nversion = "{version}"\n', encoding="utf-8"
    )
    monkeypatch.setattr(generator, "ROOT", tmp_path)

    assert generator.link_ref() == ref


def test_skill_md_links_every_reference():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    linked = {
        link.target.partition("#")[0]
        for link in find_links(text)
        if link.target.startswith("references/")
    }
    assert linked == {name for name in _skill_tree() if name.startswith("references/")}
