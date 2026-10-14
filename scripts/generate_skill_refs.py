#!/usr/bin/env python3
"""Copy the docs pages the packaged agent skill relies on into its references/.

Usage:
    just generate-skill-refs           # write the copies
    just generate-skill-refs --check   # exit 1 when a copy differs from what
                                       # this script would write

The skill ships inside the wheel (``discogs_sdk/.agents/skills/discogs-sdk/``),
so its references must match the installed version. Each copy gets a header
naming its source, and its links are rewritten: a link to another copied page
points at that copy, and every other link into this repository becomes an
absolute GitHub URL pinned to ``v<project.version>``, so an old wheel never
sends an agent to newer docs. Regenerate after every version bump.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SKILL_DIR = ROOT / "src" / "discogs_sdk" / ".agents" / "skills" / "discogs-sdk"
REFERENCES = SKILL_DIR / "references"
REPO_URL = "https://github.com/jmfontaine/discogs-sdk"

# The pages copied, by file name under docs/. SKILL.md says when to open each.
PAGES = (
    "caching.md",
    "endpoints.md",
    "errors-and-retries.md",
    "getting-started.md",
    "migrating-from-python3-discogs-client.md",
    "pagination.md",
)

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
# An inline link or image target, without a title: ](target)
_INLINE_TARGET = re.compile(r"\]\(([^()\s]+)\)")


def project_version() -> str:
    # tomllib is 3.11+, and the tooling targets 3.10; [project] holds the only
    # top-level `version = "..."` line in pyproject.toml.
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
    if match is None:
        raise SystemExit("generate_skill_refs: no version in pyproject.toml")
    return match.group(1)


def _rewrite_target(target: str, version: str) -> str:
    """The target a link in a docs page needs once copied into references/."""
    for kind in ("blob", "tree"):
        prefix = f"{REPO_URL}/{kind}/main/"
        if target.startswith(prefix):
            return f"{REPO_URL}/{kind}/v{version}/{target[len(prefix) :]}"
    if target.startswith("#") or re.match(r"^[a-z][a-z0-9+.-]*:", target):
        return target  # an in-page anchor or another site
    path, _, fragment = target.partition("#")
    resolved = (DOCS / path).resolve()
    suffix = f"#{fragment}" if fragment else ""
    if resolved.parent == DOCS and resolved.name in PAGES:
        return f"{resolved.name}{suffix}"
    relative = resolved.relative_to(ROOT).as_posix()
    kind = "tree" if resolved.is_dir() else "blob"
    return f"{REPO_URL}/{kind}/v{version}/{relative}{suffix}"


def render(page: str, version: str) -> str:
    """The reference copy of ``docs/<page>``."""
    out: list[str] = [
        (
            f"<!-- Generated from docs/{page} by scripts/generate_skill_refs.py "
            f"for v{version}; do not edit. -->"
        ),
        "",
    ]
    fence: str | None = None
    for line in (DOCS / page).read_text(encoding="utf-8").splitlines():
        match = _FENCE.match(line)
        if match and (fence is None or match.group(1).startswith(fence)):
            fence = None if fence else match.group(1)[0] * 3
        elif fence is None:
            line = _INLINE_TARGET.sub(
                lambda m: f"]({_rewrite_target(m.group(1), version)})", line
            )
        out.append(line)
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when a reference differs from the generated copy",
    )
    args = parser.parse_args()

    version = project_version()
    expected = {REFERENCES / page: render(page, version) for page in PAGES}
    unexpected = sorted(
        path for path in REFERENCES.glob("*.md") if path not in expected
    )

    if args.check:
        stale = [
            path
            for path, text in expected.items()
            if not path.is_file() or path.read_text(encoding="utf-8") != text
        ]
        for path in [*stale, *unexpected]:
            print(f"stale: {path.relative_to(ROOT)}")
        if stale or unexpected:
            print(
                "The skill references are out of date. Run `just generate-skill-refs`."
            )
            return 1
        print("The skill references are up to date.")
        return 0

    REFERENCES.mkdir(parents=True, exist_ok=True)
    for path in unexpected:
        path.unlink()
        print(f"removed {path.relative_to(ROOT)}")
    for path, text in expected.items():
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
