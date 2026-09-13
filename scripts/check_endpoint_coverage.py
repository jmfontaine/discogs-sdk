#!/usr/bin/env python3
"""Re-verify the endpoint-coverage claims in README.md.

Two independent checks:

1. Every route in the local Discogs API reference is reachable through the SDK,
   and the SDK calls no route the reference does not document. The reference
   lives in ``docs/discogs_api/`` and is git-ignored, so this runs only where
   that copy is present.

   Scope: routes only. The reference puts several operations on one route and
   documents their parameters in prose, neither of which this extracts, so a
   pass means no route has drifted -- not that every operation and parameter is
   implemented.

2. With ``--compare-upstream``, the probes behind the comparison table in
   README.md: markers that must stay present, or substrings that must stay
   absent, in the current upstream source.

   These are drift signals, not proof. A probe fires when upstream changes in a
   way that likely makes a row wrong, which is the cue to re-read its sources
   and update the table. A clean run means nothing obvious has moved.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASYNC_SRC = ROOT / "src" / "discogs_sdk" / "_async"
API_DOCS = ROOT / "docs" / "discogs_api"

UPSTREAM_REPO = "https://github.com/joalla/discogs_client.git"
UPSTREAM_SOURCES = (
    "discogs_client/client.py",
    "discogs_client/models.py",
    "discogs_client/fetchers.py",
)
# Where a response cache would have to live: every request goes through these.
UPSTREAM_REQUEST_PATH = ("discogs_client/client.py", "discogs_client/fetchers.py")

# README: the documented v2 endpoints upstream does not reach. Each gap is keyed
# by the substring whose absence from the upstream sources proves it.
UPSTREAM_ABSENT: dict[str, str] = {
    "inventory/export": "inventory export",
    "inventory/upload": "inventory upload",
    "/rating": "release ratings",
    "releases/{0}/stats": "release have/want stats",
    "collection/fields": "collection field definitions",
    "/fields/": "collection field values",
    "def create_folder(": "folder creation",
    "contributions": "user contributions",
    "submissions": "user submissions",
}

# README: "Both load data lazily, paginate automatically, support OAuth 1.0a and
# back off on HTTP 429". Keyed by the marker that implements each.
UPSTREAM_PRESENT: dict[str, str] = {
    "def fetch(": "lazy field loading",
    "class BasePaginatedResponse": "automatic pagination",
    "class OAuth2Fetcher": "OAuth 1.0a",
    "backoff_enabled": "429 backoff",
}

# README: what this SDK has and upstream does not. Keyed by a marker that must
# stay absent from the whole upstream repository.
UPSTREAM_MISSING_FEATURES: dict[str, str] = {
    "async def": "async support",
    "pydantic": "typed Pydantic response models",
}


def _normalise(path: str) -> str:
    path = re.sub(r"\{\?[^}]*\}", "", path)  # drop {?query,params} suffixes
    path = re.sub(r"\{[^}]*\}", "{}", path)  # collapse path parameters
    return path.split("?")[0].rstrip("/")


def _documented_routes() -> set[str]:
    """Route templates from the local API reference copy."""
    found = {
        _normalise(raw)
        for doc in sorted(API_DOCS.glob("*.md"))
        for raw in re.findall(r"^`(/[^`]+)`", doc.read_text(), re.MULTILINE)
    }
    found.discard("")
    return found


def _is_base_path_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_base_path"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    )


def _render(node: ast.AST, base: str | None) -> str | None:
    """Render a string literal, f-string, or bare ``self._base_path()`` call."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if base is not None and _is_base_path_call(node):
        return base
    if not isinstance(node, ast.JoinedStr):
        return None
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        elif isinstance(value, ast.FormattedValue):
            parts.append(base if base is not None and _is_base_path_call(value.value) else "{}")
    return "".join(parts)


def _base_path_of(class_node: ast.ClassDef) -> str | None:
    """The template this class's ``_base_path()`` returns, if it has one."""
    for item in class_node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "_base_path":
            for statement in ast.walk(item):
                if isinstance(statement, ast.Return) and statement.value is not None:
                    return _render(statement.value, None)
    return None


def _collect(node: ast.AST, base: str | None, out: set[str]) -> None:
    """Walk *node*, rendering route literals but never descending into f-strings."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            _collect(child, _base_path_of(child), out)
            continue
        if isinstance(child, ast.FunctionDef) and child.name == "_base_path":
            # Its template is a prefix, not a route. It counts only where a
            # caller passes self._base_path() as a request path.
            continue
        rendered = _render(child, base)
        if rendered is not None:
            if rendered.startswith("/"):
                out.add(_normalise(rendered))
            continue  # the pieces of an f-string are not routes of their own
        _collect(child, base, out)


def _sdk_routes() -> set[str]:
    found: set[str] = set()
    for source in sorted(ASYNC_SRC.rglob("*.py")):
        _collect(ast.parse(source.read_text()), None, found)
    return {route for route in found if re.fullmatch(r"/[a-z][a-z_]*(/.+)?", route) and route.count("/") > 1}


def _check_sdk() -> bool:
    documented = _documented_routes()
    reached = _sdk_routes()
    missing = sorted(documented - reached)
    unknown = sorted(reached - documented)

    print(f"Documented routes  : {len(documented)}")
    print(f"Reached by the SDK : {len(documented & reached)}")
    for route in missing:
        print(f"  UNREACHED     {route}")
    for route in unknown:
        print(f"  UNDOCUMENTED  {route}")
    if not missing and not unknown:
        print("OK: the SDK reaches every documented route, and no others.")
    return not missing and not unknown


def _mentions_caching_in_request_path(repo: Path) -> bool:
    """Whether the word appears in the modules every request goes through.

    A heuristic, like every probe here: a cache named ``responses = {}`` would
    slip past it. It catches the ordinary case and flags drift worth a look.
    """
    for name in UPSTREAM_REQUEST_PATH:
        if "cache" in (repo / name).read_text().lower():
            return True
    return False


def _check_upstream() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        clone = subprocess.run(
            ["git", "clone", "--quiet", "--depth", "1", UPSTREAM_REPO, tmp],
            capture_output=True,
            text=True,
            check=False,
        )
        if clone.returncode != 0:
            # Requested explicitly, so a clone failure is a failure to verify,
            # not a reason to certify the claims unchecked.
            print(f"\nERROR: could not clone {UPSTREAM_REPO}: {clone.stderr.strip() or 'clone failed'}")
            return False

        revision = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=tmp,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        api_source = "\n".join((Path(tmp) / name).read_text() for name in UPSTREAM_SOURCES)
        whole_repo = "\n".join(path.read_text(errors="ignore") for path in Path(tmp).rglob("*.py"))

        print(f"\npython3-discogs-client @ {revision or 'unknown'}")
        stale: list[str] = []
        for marker, claim in UPSTREAM_ABSENT.items():
            if marker in api_source:
                stale.append(f"README says it lacks {claim}, but {marker!r} is now present")
        for marker, claim in UPSTREAM_PRESENT.items():
            if marker not in api_source:
                stale.append(f"README credits it with {claim}, but {marker!r} is gone")
        for marker, claim in UPSTREAM_MISSING_FEATURES.items():
            if marker in whole_repo:
                stale.append(f"README claims it lacks {claim}, but {marker!r} is now present")
        if _mentions_caching_in_request_path(Path(tmp)):
            stale.append("README says it has no response cache, but its request path now mentions caching")

        probes = len(UPSTREAM_ABSENT) + len(UPSTREAM_PRESENT) + len(UPSTREAM_MISSING_FEATURES) + 1
        print(f"Drift probes run: {probes}")
        for line in stale:
            print(f"  STALE  {line}")
        if not stale:
            print("OK: nothing upstream has drifted away from the README.")
        return not stale


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--compare-upstream",
        action="store_true",
        help="also re-check the README comparison against python3-discogs-client (clones it)",
    )
    args = parser.parse_args()

    if not API_DOCS.is_dir():
        print(f"ERROR: {API_DOCS.relative_to(ROOT)} is missing. It holds the local API reference copy.")
        sys.exit(1)

    ok = _check_sdk()
    if args.compare_upstream:
        ok = _check_upstream() and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
