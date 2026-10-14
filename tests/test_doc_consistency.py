"""Hand-kept short copies of the docs that must not drift apart.

Each rule a caller must know has one full statement, under "Behaviors to know"
in ``docs/getting-started.md``. Two short lists of rules are written by hand
for agents: the snippet ``docs/ai-agents.md`` offers for rules files, and the
``rules`` Context7 reads from ``context7.json``. Their wording may differ, but
each must state the same rules, so every item of either list carries the key
phrases of exactly one rule in ``RULES``, and every rule appears in both.

The page index is kept twice too, in README.md (the PyPI description, with
absolute links) and in ``docs/README.md``; both must list the same pages, in
the same order, with the same descriptions.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

import pytest

from tests.conftest import REPO_ROOT

# Rule -> phrases its item must contain, compared case-insensitively with
# backticks removed, so that `DISCOGS_TOKEN` matches DISCOGS_TOKEN.
RULES: dict[str, tuple[str, ...]] = {
    "library identity": ("python3-discogs-client", "crate-ai/discogs-sdk"),
    "one client": ("one client per program",),
    "lazy loading": ("lazy proxy", "notfounderror"),
    "async proxies": ("keep the proxy",),
    "pagination cost": ("one logical get per page", "no longer parses", "break"),
    "writes": ("ambiguous", "never resubmit a create blindly"),
    "field names": ("python field names", "model.raw"),
    "http clients": ("httpx2",),
    "endpoint map": ("docs/endpoints.md",),
}

SNIPPET_SECTION = "## Agents that do not read skills"
DOCS_URL = "https://github.com/jmfontaine/discogs-sdk/blob/main/docs/"
# A Markdown list item of any kind: bullet or ordered, at any indentation.
_LIST_ITEM = re.compile(r"\s*([-*+]|\d+[.)])\s")


def _normalize(text: str) -> str:
    return text.replace("`", "").lower()


def _section(text: str, heading: str) -> str:
    """The body of the ``##`` section titled *heading*, up to the next one.

    A ``## `` line inside a code fence, such as the snippet's own heading, does
    not end the section.
    """
    lines = text.splitlines()
    assert heading in lines, f"no {heading!r} section"
    body: list[str] = []
    in_fence = False
    for line in lines[lines.index(heading) + 1 :]:
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body) + "\n"


def _one_line_items(text: str, item: str, source: str) -> list[re.Match[str]]:
    """Match every line of the list in *text* against the *item* pattern.

    Lines before the first list item are prose. From that item on, every
    non-blank line must be a whole item matching *item*, so a continuation
    line, another list marker or trailing prose fails instead of being skipped.
    """
    items: list[re.Match[str]] = []
    for line in text.splitlines():
        if not items and not _LIST_ITEM.match(line):
            continue
        if not line.strip():
            continue
        match = re.fullmatch(item, line)
        assert match is not None, (
            f"{source}: {line!r} is not a one-line list item of the expected form"
        )
        items.append(match)
    assert items, f"{source}: no list items"
    return items


def _snippet_items(text: str) -> list[str]:
    match = re.search(
        r"^```markdown\n(.*?)^```$",
        _section(text, SNIPPET_SECTION),
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, "no markdown snippet in docs/ai-agents.md"
    items = _one_line_items(match.group(1), r"- (?P<rule>.+)", "ai-agents snippet")
    return [item["rule"] for item in items]


def _snippet_rules() -> list[str]:
    return _snippet_items(
        (REPO_ROOT / "docs" / "ai-agents.md").read_text(encoding="utf-8")
    )


def _context7_rules() -> list[str]:
    config = json.loads((REPO_ROOT / "context7.json").read_text(encoding="utf-8"))
    return config["rules"]


def _rule_of(item: str) -> list[str]:
    normalized = _normalize(item)
    return [
        name
        for name, phrases in RULES.items()
        if all(phrase in normalized for phrase in phrases)
    ]


@pytest.mark.parametrize(
    ("source", "load"),
    [
        ("docs/ai-agents.md snippet", _snippet_rules),
        ("context7.json rules", _context7_rules),
    ],
)
def test_short_rule_list_states_every_rule_once(
    source: str, load: Callable[[], list[str]]
):
    items = load()
    matched: dict[str, list[str]] = {name: [] for name in RULES}
    for item in items:
        rules = _rule_of(item)
        assert len(rules) == 1, (
            f"{source}: {item!r} matches {rules or 'no rule'}; each item must carry "
            "the key phrases of exactly one rule in RULES"
        )
        matched[rules[0]].append(item)
    missing = [name for name, found in matched.items() if not found]
    repeated = [name for name, found in matched.items() if len(found) > 1]
    assert not missing, f"{source} lacks {missing}"
    assert not repeated, f"{source} states {repeated} more than once"


README_ENTRY = (
    rf"- \[(?P<title>[^\]]+)\]\({re.escape(DOCS_URL)}(?P<page>[^)#]+)\)"
    r" — (?P<description>.+)"
)
DOCS_INDEX_ENTRY = (
    r"\d+\. \[(?P<title>[^\]]+)\]\((?P<page>[^)#]+)\): (?P<description>.+)"
)


def _index(text: str, entry: str, source: str) -> list[tuple[str, str, str]]:
    return [
        (match["title"], match["page"], match["description"])
        for match in _one_line_items(text, entry, source)
    ]


def test_page_indexes_agree():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    from_readme = _index(
        _section(readme, "## Documentation"), README_ENTRY, "README.md"
    )
    from_docs = _index(docs_index, DOCS_INDEX_ENTRY, "docs/README.md")
    assert from_readme == from_docs


@pytest.mark.parametrize(
    "extra",
    [
        "  continued on a second line",
        "* another rule with a different marker",
        "+ another rule with a different marker",
    ],
)
def test_list_lines_that_are_not_whole_items_fail(extra: str):
    text = f"{SNIPPET_SECTION}\n\n```markdown\n## discogs-sdk\n- a rule\n{extra}\n```\n"
    with pytest.raises(AssertionError, match="not a one-line list item"):
        _snippet_items(text)
    index = f"# Index\n\n1. [Page](page.md): what it covers\n{extra}\n"
    with pytest.raises(AssertionError, match="not a one-line list item"):
        _index(index, DOCS_INDEX_ENTRY, "index")
