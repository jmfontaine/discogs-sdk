"""Run every ``python`` code block in README.md and docs/ against mocked HTTP.

Each document's blocks run in order in one namespace, so a fragment can use a
``client`` an earlier block created; the namespace starts with
``client = Discogs(token="test")``. Documents never share a namespace.

The blocks run under a strict respx router: a request no route matches fails
the run, and a document's routes must each be requested at least once unless
its entry in ``DOC_ROUTES`` says otherwise. Register a route only for a request
the document's examples actually send. Home and the working directory point at
a temporary directory, the pacing sleep returns at once, and every client and
injected cache the blocks create is closed afterwards.

To skip a block, put ``<!-- doc-test: skip (reason) -->`` on the line right
before its fence. The reason is required.

This catches calls and attributes that no longer exist; it cannot catch stale
prose or a comment that misstates the output.
"""

from __future__ import annotations

import asyncio
import re
import time
import traceback
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from markdown_it import MarkdownIt
from respx.router import MockRouter

from discogs_sdk import AsyncDiscogs, Discogs, ResponseCache
from tests.conftest import (
    REPO_ROOT,
    make_artist_release,
    make_collection_folder,
    make_collection_instance_created,
    make_collection_value,
    make_community_rating,
    make_listing_created,
    make_master_version,
    make_order,
    make_paginated_response,
    make_search_result,
    make_want,
    mock_router,
)
from tests.documented_payloads import ARTIST, RELEASE

_PARSER = MarkdownIt("commonmark")
_MARKER = re.compile(r"^<!--\s*doc-test:(?P<rest>.*?)-->\s*$", re.DOTALL)
_SKIP = re.compile(r"^\s*skip\s*\((?P<reason>[^()]*\S[^()]*)\)\s*$")


@dataclass(frozen=True)
class Block:
    """One ``python`` fence: its code and the file line its code starts on."""

    path: Path
    line: int
    source: str
    skip_reason: str | None = None


def collect_blocks(path: Path) -> list[Block]:
    """Every ``python`` fence in *path*, in order.

    A marker counts only as an HTML comment block of its own; marker text in
    code or inside a paragraph is ordinary text. Raises ``ValueError`` for a
    marker that lacks a reason or is not on the line right before a ``python``
    fence.
    """
    blocks: list[Block] = []
    # 0-based line of each marker comment -> its skip reason
    markers: dict[int, str] = {}
    for token in _PARSER.parse(path.read_text(encoding="utf-8")):
        if token.map is None:
            continue
        start, stop = token.map
        if token.type == "html_block":
            marker = _MARKER.match(token.content.strip())
            if marker is None:
                continue
            skip = _SKIP.match(marker["rest"])
            if skip is None or stop - start != 1:
                raise ValueError(
                    f"{path.name}:{start + 1}: write the marker on one line as "
                    "<!-- doc-test: skip (reason) -->, reason required"
                )
            markers[start] = skip["reason"].strip()
            continue
        info = token.info.split()
        if token.type == "fence" and info and info[0] == "python":
            reason = markers.pop(start - 1, None)
            blocks.append(Block(path, start + 2, token.content, reason))
    if markers:
        line = min(markers) + 1
        raise ValueError(
            f"{path.name}:{line}: a doc-test marker must sit on the line right "
            "before a ```python fence"
        )
    return blocks


def run_block(block: Block, namespace: dict[str, Any], label: str) -> None:
    """Execute *block* in *namespace*; on failure, fail naming the file and line."""
    if block.skip_reason is not None:
        return
    # Pad with newlines so tracebacks report the Markdown file's own lines.
    code = compile("\n" * (block.line - 1) + block.source, label, "exec")
    try:
        exec(code, namespace)  # noqa: S102 - running the docs is the point
    except Exception as exc:  # noqa: BLE001 - any failure is reported with its line
        frames = [
            frame
            for frame in traceback.extract_tb(exc.__traceback__)
            if frame.filename == label
        ]
        line = frames[-1].lineno if frames else block.line
        pytest.fail(f"{label}:{line}: {type(exc).__name__}: {exc}", pytrace=False)


@dataclass
class _Tracked:
    sync_clients: list[Discogs] = field(default_factory=list)
    async_clients: list[AsyncDiscogs] = field(default_factory=list)
    caches: list[ResponseCache] = field(default_factory=list)


def _recording_init(original: Callable[..., None], store: list) -> Callable[..., None]:
    def init(self, *args, **kwargs) -> None:
        store.append(self)
        original(self, *args, **kwargs)

    return init


@contextmanager
def _tracking(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Tracked]:
    """Record every client and cache built inside; close them all on the way out."""
    tracked = _Tracked()
    for cls, store in (
        (Discogs, tracked.sync_clients),
        (AsyncDiscogs, tracked.async_clients),
        (ResponseCache, tracked.caches),
    ):
        monkeypatch.setattr(cls, "__init__", _recording_init(cls.__init__, store))
    try:
        yield tracked
    finally:
        monkeypatch.undo()
        # ExitStack runs every callback even when an earlier one raises.
        with ExitStack() as stack:
            for cache in tracked.caches:
                stack.callback(cache.close)
            for client in tracked.async_clients:
                stack.callback(lambda client=client: asyncio.run(client.close()))
            for client in tracked.sync_clients:
                stack.callback(client.close)


# --- Routes -----------------------------------------------------------------
#
# One function per group of requests, so a document lists the groups its
# examples send. Release bodies come from documented_payloads.RELEASE, which
# carries the timestamps, aliases and nested mappings the examples read.

Routes = Callable[[MockRouter], None]

COLLECTION_USER = "/users/your_username"
FOLDERS = f"{COLLECTION_USER}/collection/folders"
FOLDER_RELEASE = f"{FOLDERS}/1/releases/352665"
WANT = f"{COLLECTION_USER}/wants/352665"


def _release(router: MockRouter) -> None:
    router.get("/releases/352665").respond(
        200,
        json=RELEASE,
        headers={
            "X-Discogs-Ratelimit": "60",
            "X-Discogs-Ratelimit-Used": "55",
            "X-Discogs-Ratelimit-Remaining": "5",
        },
    )


def _artist(router: MockRouter) -> None:
    router.get("/artists/3857").respond(200, json=ARTIST)


def _search(router: MockRouter) -> None:
    router.get("/database/search").respond(
        200, json=make_paginated_response("results", [make_search_result()])
    )


def _artist_releases(router: MockRouter) -> None:
    router.get("/artists/3857/releases").respond(
        200, json=make_paginated_response("releases", [make_artist_release()])
    )


def _sub_resources(router: MockRouter) -> None:
    router.get("/releases/352665/rating").respond(
        200, json=make_community_rating(release_id=352665)
    )
    _artist_releases(router)
    router.get("/masters/3719/versions").respond(
        200, json=make_paginated_response("versions", [make_master_version()])
    )


def _collection(router: MockRouter) -> None:
    router.get(FOLDERS).respond(
        200, json={"folders": [make_collection_folder(id=0, name="All")]}
    )
    router.post(FOLDERS).respond(
        201, json=make_collection_folder(id=2, name="Industrial", count=0)
    )
    router.get(f"{FOLDERS}/0/releases").respond(
        200,
        json=make_paginated_response(
            "releases",
            [
                {
                    "id": 352665,
                    "instance_id": 20,
                    "folder_id": 1,
                    "basic_information": {"id": 352665, "title": "The Downward Spiral"},
                }
            ],
        ),
    )
    router.post(FOLDER_RELEASE).respond(
        201,
        json=make_collection_instance_created(instance_id=20, username="your_username"),
    )
    router.post(f"{FOLDER_RELEASE}/instances/20/fields/1").respond(204)
    router.get(f"{COLLECTION_USER}/collection/value").respond(
        200, json=make_collection_value()
    )
    router.put(WANT).respond(201, json=make_want(id=352665))
    router.post(WANT).respond(
        200, json=make_want(id=352665, notes="Original pressing", rating=4)
    )
    router.get(f"{COLLECTION_USER}/wants").respond(
        200, json=make_paginated_response("wants", [make_want(id=352665)])
    )


def _marketplace(router: MockRouter) -> None:
    # The listing proxy for 123456789 and the fee proxy are never read, so
    # neither sends a request.
    router.post("/marketplace/listings").respond(
        201, json=make_listing_created(listing_id=41578241)
    )
    router.post("/marketplace/listings/41578241").respond(204)
    router.delete("/marketplace/listings/41578241").respond(204)
    router.get("/marketplace/orders").respond(
        200,
        json=make_paginated_response(
            "orders", [make_order(id="12345-1", status="Payment Received")]
        ),
    )


def _not_found(router: MockRouter) -> None:
    router.get("/releases/999999999").respond(
        404, json={"message": "Release not found."}
    )


@dataclass(frozen=True)
class DocRoutes:
    """What one document's examples send.

    ``routes`` answer the requests; ``requests`` is every request the blocks
    send, in order, as ``"METHOD /path"``. Pinning the sequence means no block
    can lean on a request or a cache entry another block made.
    """

    routes: tuple[Routes, ...]
    requests: tuple[str, ...]


RELEASE_GET = "GET /releases/352665"
SEARCH_GET = "GET /database/search"

COLLECTION_REQUESTS = (
    f"GET {FOLDERS}",
    f"POST {FOLDERS}",
    f"GET {FOLDERS}/0/releases",
    f"POST {FOLDER_RELEASE}",
    f"POST {FOLDER_RELEASE}/instances/20/fields/1",
    f"GET {COLLECTION_USER}/collection/value",
    f"PUT {WANT}",
    f"POST {WANT}",
    f"GET {COLLECTION_USER}/wants",
)

# Keyed by path relative to the repository root.
DOC_ROUTES: dict[str, DocRoutes] = {
    "README.md": DocRoutes(
        routes=(_release, _artist_releases, _search),
        requests=(
            # Introduction
            RELEASE_GET,
            SEARCH_GET,
            # Quick start, sync then async
            RELEASE_GET,
            "GET /artists/3857/releases",
            RELEASE_GET,
            SEARCH_GET,
        ),
    ),
    "docs/authentication.md": DocRoutes(routes=(), requests=()),
    "docs/caching.md": DocRoutes(
        routes=(_release,),
        requests=(
            # no_cache(); cache_only() raises CacheMissError before any request
            RELEASE_GET,
            # Shared SQLiteCache: only the first client reaches the API
            RELEASE_GET,
        ),
    ),
    "docs/collection-and-marketplace.md": DocRoutes(
        routes=(_collection, _marketplace),
        requests=(
            *COLLECTION_REQUESTS,
            "POST /marketplace/listings",
            "POST /marketplace/listings/41578241",
            "DELETE /marketplace/listings/41578241",
            "GET /marketplace/orders",
        ),
    ),
    "docs/concurrency.md": DocRoutes(routes=(_release,), requests=(RELEASE_GET,)),
    "docs/errors-and-retries.md": DocRoutes(
        routes=(_not_found,), requests=("GET /releases/999999999",)
    ),
    "docs/getting-started.md": DocRoutes(
        routes=(_release, _artist, _search, _sub_resources),
        requests=(
            # Fetching resources: the master and label proxies are never read
            RELEASE_GET,
            "GET /artists/3857",
            # Search
            SEARCH_GET,
            # Sub-resources
            "GET /releases/352665/rating",
            "GET /artists/3857/releases",
            "GET /masters/3719/versions",
            # Async usage
            RELEASE_GET,
            SEARCH_GET,
        ),
    ),
    "docs/models.md": DocRoutes(
        routes=(_release,),
        # Field naming, then original API values
        requests=(RELEASE_GET, RELEASE_GET),
    ),
    "docs/observability.md": DocRoutes(routes=(_release,), requests=(RELEASE_GET,)),
}


def _documents() -> list[Path]:
    candidates = [REPO_ROOT / "README.md", *sorted(REPO_ROOT.glob("docs/**/*.md"))]
    return [path for path in candidates if collect_blocks(path)]


DOCUMENTS = _documents()


def _sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point home, the cache home and the working directory at *tmp_path*."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    monkeypatch.chdir(tmp_path)
    assert Path.home() == home
    # The pacing example sleeps for 60s once the mocked budget runs low.
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


@pytest.mark.parametrize(
    "path",
    DOCUMENTS,
    ids=[str(path.relative_to(REPO_ROOT)) for path in DOCUMENTS],
)
def test_doc_examples_run(
    path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    label = str(path.relative_to(REPO_ROOT))
    doc = DOC_ROUTES.get(label)
    assert doc is not None, (
        f"{label} has python blocks but no entry in DOC_ROUTES "
        "(tests/test_doc_examples.py); add the routes its examples request"
    )
    blocks = collect_blocks(path)
    _sandbox(tmp_path, monkeypatch)
    sent_by_block: list[tuple[int, list[str]]] = []
    with (
        pytest.MonkeyPatch.context() as patch,
        _tracking(patch),
        mock_router() as router,
    ):
        for register in doc.routes:
            register(router)
        namespace: dict[str, Any] = {
            "__name__": "__main__",
            "client": Discogs(token="test"),
        }
        for block in blocks:
            before = len(router.calls)
            run_block(block, namespace, label)
            sent_by_block.append(
                (
                    block.line,
                    [
                        f"{call.request.method} {call.request.url.path}"
                        for call in router.calls[before:]
                    ],
                )
            )
    sent = [request for _, requests in sent_by_block for request in requests]
    by_block = "\n".join(
        f"  {label}:{line}: {requests}" for line, requests in sent_by_block if requests
    )
    assert sent == list(doc.requests), f"requests sent per block:\n{by_block}"


def _write(tmp_path: Path, text: str) -> Path:
    doc = tmp_path / "doc.md"
    doc.write_text(text, encoding="utf-8")
    return doc


@pytest.mark.parametrize(
    "marker",
    ["<!-- doc-test: skip -->", "<!-- doc-test: skip () -->", "<!-- doc-test: run -->"],
)
def test_skip_marker_requires_a_reason(tmp_path: Path, marker: str):
    doc = _write(tmp_path, f"# Doc\n\n{marker}\n```python\npass\n```\n")
    with pytest.raises(ValueError, match="reason required"):
        collect_blocks(doc)


def test_skip_marker_must_precede_a_python_fence(tmp_path: Path):
    doc = _write(tmp_path, "<!-- doc-test: skip (shell) -->\n\n```python\npass\n```\n")
    with pytest.raises(ValueError, match="right before"):
        collect_blocks(doc)


def test_marker_text_outside_a_comment_block_skips_nothing(tmp_path: Path):
    doc = _write(
        tmp_path,
        "Write `<!-- doc-test: skip (reason) -->` to skip.\n"
        "```python\npass\n```\n\n"
        "```markdown\n<!-- doc-test: skip (example) -->\n```\n",
    )
    [block] = collect_blocks(doc)
    assert block.skip_reason is None


def test_skipped_block_does_not_run(tmp_path: Path):
    doc = _write(
        tmp_path,
        "<!-- doc-test: skip (predecessor library) -->\n"
        "```python\nimport discogs_client\n```\n",
    )
    [block] = collect_blocks(doc)
    assert block.skip_reason == "predecessor library"
    run_block(block, {}, "doc.md")


def test_failure_names_the_file_and_line(tmp_path: Path):
    doc = _write(
        tmp_path,
        "# Doc\n\n```python\nvalue = 1\n```\n\nText.\n\n"
        "```python\nprint(value)\nvalue.missing\n```\n",
    )
    namespace: dict[str, Any] = {}
    first, second = collect_blocks(doc)
    run_block(first, namespace, "doc.md")
    with pytest.raises(pytest.fail.Exception, match=r"^doc\.md:11: AttributeError"):
        run_block(second, namespace, "doc.md")
