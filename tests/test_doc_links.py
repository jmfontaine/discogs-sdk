"""Check the links in the user documentation.

README.md is the PyPI long description, and PyPI keeps relative links as they
are, so they break there: every target in it must be absolute or an in-page
anchor.

Every local target in README.md and docs/ must exist, and so must the heading a
``#fragment`` names. Absolute URLs into this repository's ``blob/main/`` or
``tree/main/`` count as local and are checked against the working tree. Nothing
here touches the network.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from tests.conftest import REPO_ROOT
from tests.markdown_links import Link, find_anchors, find_links

README = REPO_ROOT / "README.md"
DOCUMENTS = [README, *sorted((REPO_ROOT / "docs").glob("**/*.md"))]
REPO_URLS = tuple(
    f"https://github.com/jmfontaine/discogs-sdk/{kind}/main/"
    for kind in ("blob", "tree")
)


def _non_absolute(text: str) -> list[Link]:
    return [
        link
        for link in find_links(text)
        if not link.target.startswith(("http://", "https://", "#"))
    ]


def test_readme_links_are_absolute():
    offending = [
        f"README.md:{link.line}: {link.target}"
        for link in _non_absolute(README.read_text(encoding="utf-8"))
    ]
    assert offending == []


def _resolve(doc: Path, target: str, root: Path) -> tuple[Path, str] | None:
    """The file and fragment *target* names, or None when it is not local."""
    for prefix in REPO_URLS:
        if target.startswith(prefix):
            parts = urlsplit(target[len(prefix) :])
            return root / unquote(parts.path), parts.fragment
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return None
    return (doc.parent / unquote(parts.path) if parts.path else doc), parts.fragment


def broken_links(doc: Path, root: Path = REPO_ROOT) -> list[str]:
    """Each local link in *doc* whose file or heading does not exist."""
    problems = []
    for link in find_links(doc.read_text(encoding="utf-8")):
        resolved = _resolve(doc, link.target, root)
        if resolved is None:
            continue
        path, fragment = resolved
        where = f"{doc.relative_to(root)}:{link.line}: {link.target}"
        if not path.exists():
            problems.append(f"{where}: no such file")
        elif fragment and (
            path.suffix != ".md"
            or fragment not in find_anchors(path.read_text(encoding="utf-8"))
        ):
            problems.append(f"{where}: no such heading")
    return problems


@pytest.mark.parametrize(
    "doc", DOCUMENTS, ids=[str(doc.relative_to(REPO_ROOT)) for doc in DOCUMENTS]
)
def test_local_links_resolve(doc: Path):
    assert broken_links(doc) == []


@pytest.mark.parametrize(
    ("markdown", "problem"),
    [
        ("[gone](missing.md)", "missing.md: no such file"),
        ("[gone](other.md#nowhere)", "other.md#nowhere: no such heading"),
        ("[gone](#nowhere)", "#nowhere: no such heading"),
        ("[gone](other.md#title-2)", "other.md#title-2: no such heading"),
        (
            "[gone](https://github.com/jmfontaine/discogs-sdk/blob/main/missing.md)",
            "blob/main/missing.md: no such file",
        ),
        ("[code](script.py#L3)", "script.py#L3: no such heading"),
    ],
    ids=["file", "heading", "same-page", "repeat", "repo-url", "non-markdown"],
)
def test_broken_links_are_reported(tmp_path: Path, markdown: str, problem: str):
    (tmp_path / "other.md").write_text("# Title\n\n## Title\n")
    (tmp_path / "script.py").write_text("pass\n")
    doc = tmp_path / "doc.md"
    doc.write_text(f"# Doc\n\n{markdown}\n")
    [reported] = broken_links(doc, root=tmp_path)
    assert reported.startswith("doc.md:3: ")
    assert reported.endswith(problem)


def test_resolving_links_pass(tmp_path: Path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "other.md").write_text(
        "# Title\n\n## Title\n\n## Exceptions outside `DiscogsError`\n"
    )
    doc = tmp_path / "doc.md"
    doc.write_text(
        "# Doc\n\n## Rate limits, retries & more\n\n"
        "[a](pages/other.md) [b](pages/other.md#title-1) "
        "[c](pages/other.md#exceptions-outside-discogserror) "
        "[d](#rate-limits-retries--more) [e](pages/) [f](https://example.com/x.md) "
        "[g](https://github.com/jmfontaine/discogs-sdk/tree/main/pages)\n"
    )
    assert broken_links(doc, root=tmp_path) == []


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("See [the guide](docs/guide.md).", [Link("docs/guide.md", 3)]),
        ("![logo](images/logo.png)", [Link("images/logo.png", 3)]),
        (
            "[![logo](images/logo.png)](https://example.com)",
            [Link("images/logo.png", 3)],
        ),
        (
            "See [guide].\n\n[guide]: docs/guide.md",
            [Link("docs/guide.md", 3), Link("docs/guide.md", 5)],
        ),
        ("Wrapped\n[guide](docs/guide.md)", [Link("docs/guide.md", 4)]),
        ("[unused]: <docs/guide.md>", [Link("docs/guide.md", 3)]),
        ("> [guide]: docs/guide.md", [Link("docs/guide.md", 3)]),
        ('<a href="docs/guide.md">guide</a>', [Link("docs/guide.md", 3)]),
        ("<IMG SRC='images/logo.png'>", [Link("images/logo.png", 3)]),
        ('Inline <a href="docs/guide.md">guide</a>.', [Link("docs/guide.md", 3)]),
        ("| a |\n|---|\n| [g](docs/guide.md) |", [Link("docs/guide.md", 5)]),
        (
            "Code `spans\nwrap` then [g](docs/guide.md)",
            [Link("docs/guide.md", 4)],
        ),
        ("[guide]:\n  docs/guide.md", [Link("docs/guide.md", 4)]),
        (
            "[guide]: https://example.com\n[guide]: docs/guide.md",
            [Link("docs/guide.md", 4)],
        ),
        (
            (
                '<p>\n  <a href="https://example.com"><img src="a.png"></a>\n'
                '  <img src="b.png">\n</p>'
            ),
            [Link("a.png", 4), Link("b.png", 5)],
        ),
        ("<a href>guide</a>", [Link("", 3)]),
    ],
    ids=[
        "inline",
        "image",
        "image-inside-link",
        "definition",
        "second-line-of-paragraph",
        "unused-angle-definition",
        "definition-in-quote",
        "html-block-href",
        "html-upper-case-src",
        "html-inline-href",
        "table-cell",
        "after-wrapped-code-span",
        "wrapped-definition",
        "duplicate-definition",
        "multiline-html-block",
        "bare-html-attribute",
    ],
)
def test_relative_targets_are_reported(markdown: str, expected: list[Link]):
    assert _non_absolute(f"# Title\n\n{markdown}\n") == expected


@pytest.mark.parametrize(
    "markdown",
    [
        "[home](https://github.com/jmfontaine/discogs-sdk)",
        "[plain](http://example.com/a_(b))",
        "[section](#installation)",
        "[guide]:\n  https://example.com/guide",
        '<img data-src="images/logo.png" src="https://example.com/logo.png">',
        "`[not a link](docs/guide.md)`",
        "```python\nx = d[0](docs)\n```",
        "<!-- [hidden](docs/guide.md) -->",
    ],
    ids=[
        "https",
        "http-parens",
        "anchor",
        "wrapped-definition",
        "html-data-attribute",
        "code-span",
        "fence",
        "comment",
    ],
)
def test_absolute_targets_anchors_and_code_pass(markdown: str):
    assert _non_absolute(f"# Title\n\n{markdown}\n") == []
