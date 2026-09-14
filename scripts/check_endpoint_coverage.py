#!/usr/bin/env python3
"""Re-verify the endpoint-coverage claims in README.md.

Three independent checks:

1. Every route in the local Discogs API reference is reachable through the SDK,
   and the SDK calls no route the reference does not document. The reference
   lives in ``docs/discogs_api/`` and is git-ignored, so this runs only where
   that copy is present.

   Scope: routes only. The reference puts several operations on one route and
   documents their parameters in prose, neither of which this extracts, so a
   pass means no route has drifted -- not that every operation and parameter is
   implemented.

2. Every ```json``` example block in the reference is claimed by exactly one
   ``Example`` in ``tests/documented_payloads.py``, and every claimed body
   matches its example(s) key-for-key. Runs only where the reference is
   present, for the same reason as check 1.

   Scope: shape, not values. This re-derives key sets from the reference and
   from the registered payloads/envelopes/errors and diffs them; it does not
   check that a field's example value is sensible, only that the same keys
   exist on both sides (modulo declared ``extra_keys``).

3. With ``--compare-upstream``, the probes behind the comparison table in
   README.md: markers that must stay present, or substrings that must stay
   absent, in the current upstream source.

   These are drift signals, not proof. A probe fires when upstream changes in a
   way that likely makes a row wrong, which is the cue to re-read its sources
   and update the table. A clean run means nothing obvious has moved.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ASYNC_SRC = ROOT / "src" / "discogs_sdk" / "_async"
API_DOCS = ROOT / "docs" / "discogs_api"

# ``tests`` is a package at the repo root; make it importable regardless of the
# working directory this script is invoked from.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def _render(
    node: ast.AST, base: str | None, names: dict[str, str] | None = None
) -> str | None:
    """Render a string literal, f-string, local name, or ``_base_path()`` call."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.Name) and names is not None:
        return names.get(node.id)
    if base is not None and _is_base_path_call(node):
        return base
    if not isinstance(node, ast.JoinedStr):
        return None
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        elif isinstance(value, ast.FormattedValue):
            rendered = _render(value.value, base, names)
            parts.append(rendered if rendered is not None else "{}")
    return "".join(parts)


def _base_path_of(class_node: ast.ClassDef) -> str | None:
    """The template this class's ``_base_path()`` returns, if it has one."""
    for item in class_node.body:
        if not isinstance(item, ast.FunctionDef) or item.name != "_base_path":
            continue
        names: dict[str, str] = {}
        for statement in item.body:
            if (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
            ):
                rendered = _render(statement.value, None, names)
                if rendered is not None:
                    names[statement.targets[0].id] = rendered
            elif isinstance(statement, ast.Return) and statement.value is not None:
                return _render(statement.value, None, names)
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
    return {
        route
        for route in found
        if re.fullmatch(r"/[a-z][a-z_]*(/.+)?", route) and route.count("/") > 1
    }


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


# --- Check 2: every ```json``` example in the reference, cross-checked ------

_HEADING_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$")
_REQUEST_MARKER_RE = re.compile(r"^-\s+\*\*Request\*\*\s*$")
_RESPONSE_MARKER_RE = re.compile(r"^-\s+\*\*Response\s+`(\d+)`\*\*\s*$")
_JSON_FENCE_OPEN_RE = re.compile(r"^\s*```json\s*$")
_FENCE_CLOSE_RE = re.compile(r"^\s*```\s*$")

# The reference has two recurring typos: a trailing comma before a closing
# brace/bracket, and (in a few spots) a missing comma between two sibling
# keys. Both are safe to repair with regexes: JSON object keys are always
# quoted identifiers, so "value-ending character, newline, quoted key" only
# ever occurs at the boundary between two keys, never inside a string value.
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
_MISSING_COMMA_RE = re.compile(
    r'([}\]"0-9A-Za-z])(\n\s*)"([A-Za-z_][A-Za-z0-9_]*)"\s*:'
)


class _UnparseableBlock(Exception):
    """A ```json``` block that is still invalid after both repairs."""


@dataclass(frozen=True)
class DocExample:
    """One parsed ```json``` block, identified the same way as ``Example`` in
    ``tests/documented_payloads.py`` so the two can be compared by id."""

    doc: str
    section: str
    status: str
    ordinal: int
    body: Any

    @property
    def id(self) -> str:
        return f"{self.doc}::{self.section}::{self.status}#{self.ordinal}"


def _repair_json(raw: str) -> str:
    raw = _MISSING_COMMA_RE.sub(r'\1,\2"\3":', raw)
    raw = _TRAILING_COMMA_RE.sub(r"\1", raw)
    return raw


def _doc_examples(path: Path) -> list[DocExample]:
    """Every ```json``` block in *path*, in file order.

    ``status`` follows the nearest preceding ``- **Request**`` or
    ``- **Response `NNN`**`` marker, both of which reset at every ``##``/``###``
    heading. ``ordinal`` counts repeats of the same (section, status) pair.
    """
    section = ""
    status = "request"
    counters: dict[tuple[str, str], int] = {}
    examples: list[DocExample] = []
    in_json = False
    buf: list[str] = []
    for line in path.read_text().split("\n"):
        heading = _HEADING_RE.match(line)
        if heading:
            section = heading.group(1)
            status = "request"
            continue
        if _REQUEST_MARKER_RE.match(line):
            status = "request"
            continue
        response = _RESPONSE_MARKER_RE.match(line)
        if response:
            status = response.group(1)
            continue
        if not in_json:
            if _JSON_FENCE_OPEN_RE.match(line):
                in_json = True
                buf = []
            continue
        if not _FENCE_CLOSE_RE.match(line):
            buf.append(line)
            continue
        in_json = False
        raw = "\n".join(buf)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            try:
                body = json.loads(_repair_json(raw))
            except json.JSONDecodeError as exc:
                raise _UnparseableBlock(
                    f"{path.name}, section {section!r} ({status}): {exc}"
                ) from exc
        key = (section, status)
        ordinal = counters.get(key, 0)
        counters[key] = ordinal + 1
        examples.append(DocExample(path.name, section, status, ordinal, body))
    return examples


def _documented_examples() -> dict[str, DocExample]:
    return {
        example.id: example
        for doc in sorted(API_DOCS.glob("*.md"))
        for example in _doc_examples(doc)
    }


def _walk_path(value: Any, segments: tuple[str, ...]) -> list[Any]:
    """Every value reachable from *value* by following *segments*, descending
    through lists at every step -- a segment names a dict key, never a list
    index, so a list in the way is expanded rather than consumed."""
    if isinstance(value, list):
        result: list[Any] = []
        for item in value:
            result.extend(_walk_path(item, segments))
        return result
    if not segments:
        return [value]
    if isinstance(value, dict) and segments[0] in value:
        return _walk_path(value[segments[0]], segments[1:])
    return []


def _key_tree(value: Any, prefix: str = "") -> set[str]:
    """Dotted paths to every key reachable in *value*.

    List-aware: a list contributes the union of its elements' key trees under
    its own path, exactly how ``extra_keys`` and ``items_path`` address it
    (``items.release.id``, never ``items.0.release.id``).
    """
    keys: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            child = f"{prefix}.{k}" if prefix else k
            keys.add(child)
            keys |= _key_tree(v, child)
    elif isinstance(value, list):
        for item in value:
            keys |= _key_tree(item, prefix)
    return keys


def _empty_container_prefixes(value: Any, prefix: str = "") -> set[str]:
    """Dotted paths of keys documented as an empty list or dict.

    Deliberate, not an oversight: an empty container carries no key-shape
    information (unioning across zero elements yields no nested keys for it),
    so its children must not be flagged as an undocumented payload key --
    "no assertion possible" is not the same as "absent from the reference".
    """
    prefixes: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            child = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (list, dict)) and not v:
                prefixes.add(child)
            else:
                prefixes |= _empty_container_prefixes(v, child)
    elif isinstance(value, list):
        for item in value:
            prefixes |= _empty_container_prefixes(item, prefix)
    return prefixes


def _under_empty_container(key: str, empty_prefixes: set[str]) -> bool:
    return any(key == p or key.startswith(f"{p}.") for p in empty_prefixes)


def _resolved_key_tree(
    examples: tuple[Any, ...], found: dict[str, DocExample]
) -> tuple[set[str], set[str]]:
    """The unioned, recursive key tree of every claimed ``Example``, plus the
    dotted paths of any containers documented as empty."""
    resolved: list[Any] = []
    for example in examples:
        segments = tuple(p for p in example.path.split(".") if p)
        resolved.extend(_walk_path(found[example.id].body, segments))
    return _key_tree(resolved, ""), _empty_container_prefixes(resolved, "")


def _check_examples() -> bool:
    """Cross-check ``tests/documented_payloads.py`` against the reference.

    Every ```json``` block in the reference must be claimed by exactly one
    Example across DOCUMENTED_PAYLOADS, DOCUMENTED_ENVELOPES and
    DOCUMENTED_ERRORS, and every claimed payload/envelope/error body must
    match its example(s) key-for-key (payloads only; dynamic payloads and
    envelope/error bodies are checked structurally, not key-for-key).
    """
    from tests import documented_payloads as docs

    try:
        found = _documented_examples()
    except _UnparseableBlock as exc:
        print(f"\nERROR: unparseable example block in {exc}")
        return False

    # Two payloads may claim the same block at different paths — an item and the
    # object nested inside it — so ownership is keyed by (example id, path).
    # Record every owner rather than letting the last writer win.
    claimed: dict[str, list[str]] = {}
    owners_by_target: dict[tuple[str, str], list[str]] = {}
    for name, payload in docs.DOCUMENTED_PAYLOADS.items():
        for example in payload.examples:
            claimed.setdefault(example.id, []).append(f"payload {name!r}")
            owners_by_target.setdefault((example.id, example.path), []).append(name)
    for name, envelope in docs.DOCUMENTED_ENVELOPES.items():
        claimed.setdefault(envelope.example.id, []).append(f"envelope {name!r}")
    for name, error in docs.DOCUMENTED_ERRORS.items():
        claimed.setdefault(error.example.id, []).append(f"error {name!r}")

    unclaimed = sorted(set(found) - set(claimed))
    orphaned = sorted(set(claimed) - set(found))
    duplicated = sorted(
        (target, names) for target, names in owners_by_target.items() if len(names) > 1
    )

    problems: list[str] = []
    for example_id in unclaimed:
        problems.append(f"UNCLAIMED  {example_id} is not claimed by any Example")
    for example_id in orphaned:
        owners = ", ".join(claimed[example_id])
        problems.append(f"MISSING    {example_id}, claimed by {owners}")
    for (example_id, path), names in duplicated:
        where = f"{example_id} at {path!r}" if path else example_id
        problems.append(f"DUPLICATE  {where} is claimed by {', '.join(sorted(names))}")

    for name, payload in sorted(docs.DOCUMENTED_PAYLOADS.items()):
        if any(example.id not in found for example in payload.examples):
            continue  # already reported above
        if payload.dynamic:
            continue
        documented_keys, empty_prefixes = _resolved_key_tree(payload.examples, found)
        payload_keys = _key_tree(payload.payload, "")
        for key in sorted(documented_keys - payload_keys):
            problems.append(f"KEY        {name}: documented key {key!r} missing")
        extra = payload_keys - documented_keys - payload.extra_keys
        for key in sorted(extra):
            if _under_empty_container(key, empty_prefixes):
                continue
            problems.append(f"KEY        {name}: payload key {key!r} not in reference")

    for name, envelope in sorted(docs.DOCUMENTED_ENVELOPES.items()):
        doc_example = found.get(envelope.example.id)
        if doc_example is None:
            continue  # already reported above
        body = doc_example.body
        if "pagination" not in body:
            problems.append(f"ENVELOPE   {name}: example body has no 'pagination'")
        if envelope.items_key not in body:
            problems.append(
                f"ENVELOPE   {name}: example body has no {envelope.items_key!r}"
            )
        elif envelope.items_path is not None and not _walk_path(
            body, envelope.items_path
        ):
            problems.append(
                f"ENVELOPE   {name}: items_path {envelope.items_path} did not resolve"
            )
        if envelope.item not in docs.DOCUMENTED_PAYLOADS:
            problems.append(
                f"ENVELOPE   {name}: item {envelope.item!r} is not documented"
            )

    for name, error in sorted(docs.DOCUMENTED_ERRORS.items()):
        doc_example = found.get(error.example.id)
        if doc_example is None:
            continue  # already reported above
        body = doc_example.body
        if set(body) != {"message"}:
            problems.append(
                f"ERROR      {name}: body is not {{'message': ...}}: {sorted(body)}"
            )
        if error.example.status != str(error.status):
            problems.append(
                f"ERROR      {name}: status {error.status} != example status "
                f"{error.example.status!r}"
            )

    print(f"\nExample blocks in the reference    : {len(found)}")
    print(f"Claimed by documented_payloads.py  : {len(claimed)}")
    for problem in problems:
        print(f"  {problem}")
    if not problems:
        print("OK: every example is claimed, and every body matches it.")
    return not problems


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
            print(
                f"\nERROR: could not clone {UPSTREAM_REPO}: "
                f"{clone.stderr.strip() or 'clone failed'}"
            )
            return False

        revision = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=tmp,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        api_source = "\n".join(
            (Path(tmp) / name).read_text() for name in UPSTREAM_SOURCES
        )
        whole_repo = "\n".join(
            path.read_text(errors="ignore") for path in Path(tmp).rglob("*.py")
        )

        print(f"\npython3-discogs-client @ {revision or 'unknown'}")
        stale: list[str] = []
        for marker, claim in UPSTREAM_ABSENT.items():
            if marker in api_source:
                stale.append(
                    f"README says it lacks {claim}, but {marker!r} is now present"
                )
        for marker, claim in UPSTREAM_PRESENT.items():
            if marker not in api_source:
                stale.append(f"README credits it with {claim}, but {marker!r} is gone")
        for marker, claim in UPSTREAM_MISSING_FEATURES.items():
            if marker in whole_repo:
                stale.append(
                    f"README claims it lacks {claim}, but {marker!r} is now present"
                )
        if _mentions_caching_in_request_path(Path(tmp)):
            stale.append(
                "README says it has no response cache, but its request path "
                "now mentions caching"
            )

        probes = (
            len(UPSTREAM_ABSENT)
            + len(UPSTREAM_PRESENT)
            + len(UPSTREAM_MISSING_FEATURES)
            + 1
        )
        print(f"Drift probes run: {probes}")
        for line in stale:
            print(f"  STALE  {line}")
        if not stale:
            print("OK: nothing upstream has drifted away from the README.")
        return not stale


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--compare-upstream",
        action="store_true",
        help=(
            "also re-check the README comparison against "
            "python3-discogs-client (clones it)"
        ),
    )
    args = parser.parse_args()

    if not API_DOCS.is_dir():
        print(
            f"ERROR: {API_DOCS.relative_to(ROOT)} is missing. "
            "It holds the local API reference copy."
        )
        sys.exit(1)

    sdk_ok = _check_sdk()
    examples_ok = _check_examples()
    ok = sdk_ok and examples_ok
    if args.compare_upstream:
        ok = _check_upstream() and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
