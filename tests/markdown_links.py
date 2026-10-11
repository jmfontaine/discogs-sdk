"""Find the link and image targets, and the heading anchors, in a Markdown file.

Covers inline links and images (``[text](target)``, ``![alt](target)``),
reference-style definitions (``[label]: target``, used or not) and the
``href``/``src`` attributes of raw HTML. Code blocks, code spans and HTML
comments yield nothing. The file is parsed as CommonMark with tables, close to
what GitHub and PyPI render.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from itertools import pairwise

from markdown_it import MarkdownIt

_PARSER = MarkdownIt("commonmark").enable("table")
_HTML_URL_ATTRIBUTES = frozenset({"href", "src"})


@dataclass(frozen=True)
class Link:
    """One link or image target and the 1-based line it starts on."""

    target: str
    line: int


class _AttributeCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # HTMLParser lower-cases attribute names, so HREF counts and data-src
        # does not. It also routes a self-closing <img ... /> here. A bare
        # attribute (<a href>) comes as None; HTML reads it as "".
        line = self.getpos()[0]
        self.targets.extend(
            (value or "", line) for name, value in attrs if name in _HTML_URL_ATTRIBUTES
        )


def _html_targets(html: str) -> list[tuple[str, int]]:
    """Each href/src in *html* with its 1-based line within *html*."""
    collector = _AttributeCollector()
    collector.feed(html)
    collector.close()
    return collector.targets


def _locate(lines: list[str], start: int, stop: int, needle: str) -> int:
    """The first 0-based line in ``lines[start:stop]`` containing *needle*.

    Falls back to *start* when the parser normalized the target so that it no
    longer appears verbatim, such as a percent-encoded space.
    """
    for index in range(start, stop):
        if needle in lines[index]:
            return index
    return start


def find_links(text: str) -> list[Link]:
    """Return every link and image target in *text*, in document order."""
    lines = text.splitlines()
    env: dict = {}
    found: list[Link] = []
    for block in _PARSER.parse(text, env):
        if block.map is None:
            continue
        first, stop = block.map
        if block.type == "html_block":
            found.extend(
                Link(target, first + line)
                for target, line in _html_targets(block.content)
            )
        # Inline tokens carry no position of their own: find each target in
        # the block's source lines, moving forward so repeats map in order.
        cursor = first
        for token in block.children or []:
            if token.type == "html_inline":
                tag_start = token.content.split("\n", 1)[0]
                cursor = _locate(lines, cursor, stop, tag_start)
                found.extend(
                    Link(target, cursor + line)
                    for target, line in _html_targets(token.content)
                )
            elif token.type in ("link_open", "image"):
                target = str(
                    token.attrs["href" if token.type == "link_open" else "src"]
                )
                cursor = _locate(lines, cursor, stop, target)
                found.append(Link(target, cursor + 1))
    # A label defined twice keeps its first definition in "references"; the
    # later ones still render nowhere but are checked all the same.
    definitions = [*env.get("references", {}).values(), *env.get("duplicate_refs", [])]
    for definition in definitions:
        first, stop = definition["map"]
        line = _locate(lines, first, stop, definition["href"]) + 1
        found.append(Link(definition["href"], line))
    return sorted(found, key=lambda link: link.line)


def find_anchors(text: str) -> set[str]:
    """The ``#fragment`` GitHub gives each heading in *text*.

    GitHub lower-cases the heading's text, drops everything but letters,
    digits, ``_``, ``-`` and spaces, turns spaces into ``-``, and appends
    ``-1``, ``-2``, … to repeats.
    """
    tokens = _PARSER.parse(text)
    seen: dict[str, int] = {}
    anchors: set[str] = set()
    for heading, inline in pairwise(tokens):
        if heading.type != "heading_open":
            continue
        title = "".join(
            child.content
            for child in inline.children or []
            if child.type in ("text", "code_inline")
        )
        slug = re.sub(r"[^\w\- ]", "", title.strip().lower()).replace(" ", "-")
        repeat = seen.get(slug, 0)
        seen[slug] = repeat + 1
        anchors.add(f"{slug}-{repeat}" if repeat else slug)
    return anchors
