"""Check the links in the user documentation.

README.md is the PyPI long description, and PyPI keeps relative links as they
are, so they break there: every target in it must be absolute or an in-page
anchor.
"""

from __future__ import annotations

import pytest

from tests.conftest import REPO_ROOT
from tests.markdown_links import Link, find_links

README = REPO_ROOT / "README.md"


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
