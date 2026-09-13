#!/usr/bin/env python3
"""Refresh docs/discogs_api from the official Discogs API reference.

Usage:
    just update-api-docs           # report drift without writing
    just update-api-docs --diff    # also print unified diffs
    just update-api-docs --check   # report drift, exit 1 when files differ
    just update-api-docs --write   # overwrite the local reference

docs/discogs_api is git-ignored, so overwriting it cannot be undone. Writing is
therefore opt-in: without --write this script only reports what would change.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote, unquote

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify

if TYPE_CHECKING:
    from collections.abc import Iterable

DOCS_URL = "https://www.discogs.com/developers"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "discogs_api"

# KLUDGE: Cloudflare serves a JS challenge to clients whose TLS handshake does
# not look like a browser, so httpx2, curl, and urllib get a 403. curl_cffi
# replays a browser handshake. Replace it if Discogs publishes the reference in
# a machine-readable form (an OpenAPI document or documentation repository).
IMPERSONATIONS = ("chrome", "safari", "firefox")
PAGE_SLUG_RE = re.compile(r"page\(\) == '([^']+)'")
HEADER_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z-]*: ")
ENDPOINT_ROUTE_RE = re.compile(r"^`/[^`\n]+`$", re.MULTILINE)
REQUIRED_PAGE_SLUGS = frozenset({"authentication", "database", "home"})
# Upstream <h1> text names the output file, so it must be a safe single path
# component: no empty value, no separator, no leading dot, no traversal.
PAGE_TITLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '()&,-]*$")
MARKDOWN_FRAGMENT_RE = re.compile(r"\]\(([^)#]+\.md)#([^)]+)\)")


def fetch_html(url: str = DOCS_URL) -> str:
    """Fetch the reference page with a browser-like TLS fingerprint."""
    from curl_cffi import requests

    last_error = ""
    for profile in IMPERSONATIONS:
        try:
            response = requests.get(url, impersonate=profile, timeout=60)
        except requests.RequestsError as error:
            last_error = f"{profile}: {error}"
            continue
        if response.status_code == 200 and "Just a moment" not in response.text[:512]:
            return response.text
        last_error = f"{profile}: HTTP {response.status_code}"
    raise SystemExit(
        f"ERROR: could not fetch {url} ({last_error}).\n"
        "Cloudflare rejected every browser profile. Try again later, or use "
        "--from-html with a copy saved from a browser."
    )


def _decode_cf_email(encoded: str) -> str:
    """Undo Cloudflare's XOR email obfuscation."""
    key = int(encoded[:2], 16)
    return "".join(
        chr(int(encoded[index : index + 2], 16) ^ key)
        for index in range(2, len(encoded), 2)
    )


def _title(slug: str) -> str:
    return slug.replace("-", " ").title()


def _page_filename(title: str) -> str:
    """Reject upstream page titles that are not safe path components."""
    if not PAGE_TITLE_RE.match(title):
        raise SystemExit(
            f"ERROR: unsafe documentation page title: {title!r}. "
            "Refusing to replace the local reference."
        )
    return f"{title}.md"


def _rewrite_page_link(href: str) -> str:
    """Turn the site's JavaScript routes into relative Markdown links."""
    if not href.startswith("#page:"):
        return href
    page, separator, fragment = href.removeprefix("#page:").partition(",header:")
    anchor = f"#{fragment}" if separator else ""
    destination = quote(f"{_title(page)}.md")
    return f"{destination}{anchor}" if page else href


def _language(pre: Tag) -> str:
    code = pre.find("code")
    if isinstance(code, Tag):
        for class_name in code.get("class") or ():
            if class_name.startswith("language-"):
                language = class_name.removeprefix("language-")
                return "" if language == "no-highlight" else language
    text = pre.get_text().lstrip()
    if text.startswith(("{", "[")):
        return "json"
    return "http" if HEADER_LINE_RE.match(text) else ""


def _prepare_page(node: Tag) -> None:
    """Remove site UI while preserving the reference content."""
    for element in node.select(
        "a.btn-default, a.permalink, button, div.clearfix, i.fa, "
        "[style*='display: none']"
    ):
        element.decompose()
    for divider in node.find_all("hr", recursive=False):
        divider.decompose()
    for line_break in node.select("pre br"):
        line_break.replace_with("\n")
    for link in node.find_all("a"):
        classes = set(link.get("class") or ())
        if "__cf_email__" in classes:
            link.replace_with(_decode_cf_email(str(link.get("data-cfemail", ""))))
        elif href := link.get("href"):
            link["href"] = _rewrite_page_link(str(href))


def _add_source_anchors(text: str, node: Tag) -> str:
    """Retain the source IDs used by rewritten cross-page links."""
    anchors: dict[str, list[str]] = {}
    for heading in node.find_all(re.compile(r"^h[1-6]$")):
        identifier = heading.get("id")
        if identifier:
            marker = f"{'#' * int(heading.name[1])} {heading.get_text(strip=True)}"
            anchors.setdefault(marker, []).append(str(identifier))
    for section in node.find_all("section", id=True):
        identifier = section.get("id")
        method = section.find("a", class_="btn-xs")
        if not identifier or not isinstance(method, Tag):
            continue
        href = method.get("href")
        if href:
            marker = f"[{method.get_text(strip=True)}]({href})"
            anchors.setdefault(marker, []).append(str(identifier))

    output: list[str] = []
    for line in text.splitlines():
        if identifiers := anchors.get(line):
            output.extend(
                (f'<a id="{escape(identifiers.pop(0), quote=True)}"></a>', "")
            )
        output.append(line)
    return "\n".join(output)


def _page_nodes(soup: BeautifulSoup) -> list[tuple[str, str, Tag]]:
    """Validate and return the top-level documentation page containers."""
    pages: list[tuple[str, str, Tag]] = []
    slugs: set[str] = set()
    titles: set[str] = set()
    for node in soup.find_all("div", attrs={"data-bind": PAGE_SLUG_RE}):
        if node.find_parent("div", attrs={"data-bind": PAGE_SLUG_RE}):
            continue
        match = PAGE_SLUG_RE.search(str(node.get("data-bind")))
        heading = node.find("h1")
        if match is None or not isinstance(heading, Tag):
            raise SystemExit("ERROR: a documentation page has no slug or title.")
        slug = match[1]
        title = heading.get_text(strip=True)
        if slug in slugs or title in titles:
            raise SystemExit(
                f"ERROR: duplicate documentation page slug or title: {slug!r}, "
                f"{title!r}."
            )
        slugs.add(slug)
        titles.add(title)
        pages.append((slug, title, node))

    if len(pages) < 2:
        raise SystemExit(
            "ERROR: the fetched HTML contained fewer than two documentation "
            "pages. Refusing to replace the local reference."
        )
    if missing := REQUIRED_PAGE_SLUGS - slugs:
        raise SystemExit(
            "ERROR: the fetched HTML is missing required documentation pages: "
            f"{', '.join(sorted(missing))}. Refusing to replace the local reference."
        )
    return pages


def _validate_fragment_links(pages: dict[str, str]) -> None:
    """Require every generated cross-page fragment to name a source anchor."""
    missing: list[str] = []
    for source, text in pages.items():
        for target, fragment in MARKDOWN_FRAGMENT_RE.findall(text):
            target_text = pages.get(unquote(target))
            anchor = f'<a id="{escape(fragment, quote=True)}"></a>'
            if target_text is None or anchor not in target_text:
                missing.append(f"{source}: {target}#{fragment}")
    if missing:
        raise SystemExit(
            "ERROR: generated Markdown contains missing fragment targets:\n  "
            + "\n  ".join(sorted(missing))
        )


def render_pages(html: str) -> dict[str, str]:
    """Validate and convert every documentation page to Markdown."""
    soup = BeautifulSoup(html, "html.parser")
    pages: dict[str, str] = {}
    for _, title, node in _page_nodes(soup):
        _prepare_page(node)
        text = markdownify(
            str(node),
            bullets="-",
            code_language_callback=_language,
            heading_style="ATX",
            newline_style="BACKSLASH",
        )
        text = _add_source_anchors(text, node)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        pages[_page_filename(title)] = f"{text}\n"
    if not any(ENDPOINT_ROUTE_RE.search(text) for text in pages.values()):
        raise SystemExit(
            "ERROR: the fetched documentation contains no endpoint routes. "
            "Refusing to replace the local reference."
        )
    _validate_fragment_links(pages)
    return pages


def _diff(name: str, old: str, new: str) -> list[str]:
    return list(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
        )
    )


def _counts(diff: Iterable[str]) -> tuple[int, int]:
    added = removed = 0
    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="report drift without writing; exit 1 when files differ",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="overwrite docs/discogs_api; required to change any file",
    )
    parser.add_argument(
        "--diff", action="store_true", help="print a unified diff for each change"
    )
    parser.add_argument(
        "--from-html",
        type=Path,
        metavar="PATH",
        help="render saved HTML instead of fetching it",
    )
    args = parser.parse_args()

    html = (
        args.from_html.read_text(encoding="utf-8") if args.from_html else fetch_html()
    )
    source = str(args.from_html) if args.from_html else DOCS_URL
    pages = render_pages(html)
    existing = {path.name: path for path in sorted(OUTPUT_DIR.glob("*.md"))}
    print(f"Source: {source} ({len(html):,} bytes, {len(pages)} pages)")

    changes: list[tuple[str, str, list[str]]] = []
    for name, new in sorted(pages.items()):
        path = existing.pop(name, None)
        old = path.read_text(encoding="utf-8") if path else ""
        if old == new:
            print(f"  unchanged  {name}")
            continue
        diff = _diff(name, old, new)
        added, removed = _counts(diff)
        state = "updated" if path else "new"
        print(f"  {state:<9}  {name}  +{added} -{removed}")
        changes.append((state, name, diff))

    for name, path in existing.items():
        diff = _diff(name, path.read_text(encoding="utf-8"), "")
        print(f"  removed    {name}  -{_counts(diff)[1]}")
        changes.append(("removed", name, diff))

    if args.diff:
        for _, _, diff in changes:
            print(f"\n{''.join(diff)}", end="")

    if not changes:
        print("\nThe local reference matches upstream.")
        return 0
    if args.check:
        print(f"\n{len(changes)} page(s) differ. Run `just update-api-docs --write`.")
        return 1
    if not args.write:
        print(
            f"\n{len(changes)} page(s) differ, none written. docs/discogs_api is "
            "git-ignored, so overwriting it cannot be undone; rerun with --write "
            "to apply."
        )
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for state, name, _ in changes:
        path = OUTPUT_DIR / name
        if state == "removed":
            path.unlink()
        else:
            path.write_text(pages[name], encoding="utf-8")
    print(f"\nWrote {len(changes)} page(s) to {OUTPUT_DIR}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
