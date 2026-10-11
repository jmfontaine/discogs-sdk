"""tests/async and tests/sync must test the same things under the same names.

Both trees are written by hand, while the sync client is generated from the async
one, so a test present in only one tree leaves that client's behaviour unchecked.
Every test is identified by ``(file, class, function)``; a test in one tree needs a
twin of the same identity in the other, unless ``ALLOWED`` says why it cannot have
one.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import TypeGuard

TESTS = Path(__file__).resolve().parent
TREES = ("async", "sync")

# (file, class, function); class is "" for a module-level test.
Identity = tuple[str, str, str]

AWAIT_ONLY = (
    "awaiting a proxy has no sync counterpart: the sync proxy resolves on attribute "
    "access instead, which the sync-only AUTO_RESOLVE tests cover"
)
AUTO_RESOLVE = (
    "the sync proxy resolves on attribute access; the async one is awaited instead, "
    "which the async-only AWAIT_ONLY tests cover"
)
CONCURRENT_AWAITS = (
    "concurrent awaits of one proxy share a request; only an async proxy is awaited"
)
PRIVATE_PROBES = (
    "only the sync proxy resolves on attribute access, so only it must refuse to "
    "spend a request on a tool's _-prefixed probe"
)
CONCURRENCY = (
    "bypass state is per task in the async client and per thread in the sync one; "
    "each tree tests its own concurrency model"
)
ABORTED_CLOSE = (
    "the same check with each client's own abort: CancelledError for the async "
    "client, KeyboardInterrupt for the sync one"
)
OFFLOAD = (
    "the async client runs cache and upload file I/O on worker threads, the sync one "
    "on the calling thread; each tree pins its own placement, and only the async "
    "client can stall other tasks"
)
GENERATED_SURFACE = "checks the generated sync code itself, which has no async twin"
MODEL_ONLY = (
    "exercises a Pydantic model shared by both clients, not generated code, so one "
    "copy is enough"
)

# (reason, tree, file, class, functions) for each test that may have no twin.
ALLOWED: list[tuple[str, str, str, str, tuple[str, ...]]] = [
    (
        AWAIT_ONLY,
        "async",
        "test_lazy.py",
        "TestResolve",
        ("test_await_triggers_http", "test_second_await_cached", "test_error_raises"),
    ),
    (
        AWAIT_ONLY,
        "async",
        "test_lazy.py",
        "TestAttributeAccess",
        ("test_data_attr_before_await_raises", "test_data_attr_after_await"),
    ),
    (
        AWAIT_ONLY,
        "async",
        "test_lazy.py",
        "TestGetItem",
        ("test_getitem_before_await_raises", "test_getitem_after_await"),
    ),
    (
        AWAIT_ONLY,
        "async",
        "test_lazy.py",
        "TestReadOnly",
        ("test_field_assignment_raises_after_await",),
    ),
    (
        AWAIT_ONLY,
        "async",
        "test_lazy.py",
        "TestTypedSurface",
        ("test_await_returns_the_concrete_model",),
    ),
    (
        AWAIT_ONLY,
        "async",
        "test_releases.py",
        "TestReleasePriceSuggestions",
        ("test_price_suggestions_subscript_after_await",),
    ),
    (
        CONCURRENT_AWAITS,
        "async",
        "test_lazy.py",
        "TestConcurrentAwaits",
        (
            "test_three_awaiters_send_one_request",
            "test_failure_reaches_every_awaiter_and_is_not_cached",
            "test_failed_fetch_is_not_replayed_before_its_slot_clears",
            "test_cancelling_one_awaiter_leaves_the_others",
            "test_request_outlives_cancelling_every_awaiter",
            "test_unawaited_failure_is_not_reported_as_unretrieved",
        ),
    ),
    (AUTO_RESOLVE, "sync", "test_lazy.py", "TestCreation", ("test_no_await_method",)),
    (
        AUTO_RESOLVE,
        "sync",
        "test_lazy.py",
        "TestAutoResolve",
        (
            "test_attribute_access_triggers_http",
            "test_second_access_cached",
            "test_error_raises",
        ),
    ),
    (
        AUTO_RESOLVE,
        "sync",
        "test_lazy.py",
        "TestGetItem",
        ("test_getitem_resolves_and_raises_not_subscriptable",),
    ),
    (
        AUTO_RESOLVE,
        "sync",
        "test_lazy.py",
        "TestReadOnly",
        ("test_field_assignment_raises_after_resolution",),
    ),
    (
        AUTO_RESOLVE,
        "sync",
        "test_lazy.py",
        "TestTypedSurface",
        ("test_attribute_access_resolves_the_model",),
    ),
    (
        PRIVATE_PROBES,
        "sync",
        "test_lazy.py",
        "TestPrivateNameProbes",
        (
            "test_probes_send_no_request",
            "test_deepcopy_sends_no_request",
            "test_probes_are_not_delegated_after_resolution",
        ),
    ),
    (
        CONCURRENCY,
        "async",
        "test_client.py",
        "TestCacheBranch",
        ("test_concurrent_tasks_keep_independent_bypass_state",),
    ),
    (
        CONCURRENCY,
        "sync",
        "test_client.py",
        "TestCacheBranch",
        ("test_threads_keep_independent_bypass_state",),
    ),
    (
        ABORTED_CLOSE,
        "async",
        "test_client.py",
        "TestCacheOwnership",
        (
            "test_cancelled_http_close_still_closes_owned_cache",
            "test_cancelled_http_close_leaves_injected_cache_open",
        ),
    ),
    (
        ABORTED_CLOSE,
        "sync",
        "test_client.py",
        "TestCacheOwnership",
        (
            "test_interrupted_http_close_still_closes_owned_cache",
            "test_interrupted_http_close_leaves_injected_cache_open",
        ),
    ),
    (
        OFFLOAD,
        "async",
        "test_cache_offload.py",
        "TestCacheCalls",
        (
            "test_lookup_store_and_clear_run_on_worker_threads",
            "test_slow_lookup_does_not_stall_other_tasks",
        ),
    ),
    (
        OFFLOAD,
        "async",
        "test_cache_offload.py",
        "TestUploadFileRead",
        ("test_file_is_read_on_a_worker_thread",),
    ),
    (
        OFFLOAD,
        "sync",
        "test_cache_offload.py",
        "TestCacheCalls",
        ("test_lookup_store_and_clear_run_on_the_calling_thread",),
    ),
    (
        GENERATED_SURFACE,
        "sync",
        "test_client.py",
        "TestGeneratedSurface",
        ("test_docstring_describes_sync_usage", "test_package_exports_the_sync_client"),
    ),
    *(
        (MODEL_ONLY, "async", file, cls, ("test_required_fields", "test_extra_allow"))
        for file, cls in [
            ("test_artists.py", "TestArtistModel"),
            ("test_exports.py", "TestExportModel"),
            ("test_labels.py", "TestLabelModel"),
            ("test_lists.py", "TestListModel"),
            ("test_marketplace.py", "TestListingModel"),
            ("test_masters.py", "TestMasterModel"),
            ("test_search.py", "TestSearchResultModel"),
            ("test_wantlist.py", "TestWantModel"),
        ]
    ),
    (
        MODEL_ONLY,
        "async",
        "test_collection.py",
        "TestCollectionModels",
        ("test_folder_required_fields", "test_folder_extra_allow"),
    ),
]

# (tree, file, class, function) -> why the other tree has no twin.
_ALLOWED: dict[tuple[str, str, str, str], str] = {
    (tree, file, cls, function): reason
    for reason, tree, file, cls, functions in ALLOWED
    for function in functions
}


def _is_test(node: ast.stmt) -> TypeGuard[ast.FunctionDef | ast.AsyncFunctionDef]:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
        node.name.startswith("test")
    )


def _tests(body: list[ast.stmt], cls: str) -> Iterator[tuple[str, str]]:
    """``(class, function)`` per test in ``body``; nested classes join with ``::``."""
    for node in body:
        if _is_test(node):
            yield cls, node.name
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            yield from _tests(node.body, f"{cls}::{node.name}" if cls else node.name)


def collect(tree: str) -> set[Identity]:
    """Every ``(file, class, function)`` test in ``tests/<tree>/test_*.py``."""
    found: set[Identity] = set()
    for path in sorted((TESTS / tree).glob("test_*.py")):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found.update((path.name, *test) for test in _tests(module.body, ""))
    return found


def _describe(tree: str, test: Identity) -> str:
    file, cls, function = test
    return "::".join(part for part in (f"tests/{tree}/{file}", cls, function) if part)


def unmatched(collected: dict[str, set[Identity]]) -> list[str]:
    """One line per test without a twin in the other tree or an allowance."""
    problems = []
    for tree, other in (TREES, TREES[::-1]):
        for test in sorted(collected[tree] - collected[other]):
            if (tree, *test) not in _ALLOWED:
                problems.append(
                    f"{_describe(tree, test)} has no counterpart in "
                    f"tests/{other}/{test[0]}"
                )
    return problems


def stale_allowances(collected: dict[str, set[Identity]]) -> list[str]:
    """One line per allowance that no longer describes a one-sided test."""
    problems = []
    for tree, file, cls, function in sorted(_ALLOWED):
        other = TREES[1 - TREES.index(tree)]
        test = (file, cls, function)
        if test not in collected[tree]:
            problems.append(f"{_describe(tree, test)} is allow-listed but missing")
        elif test in collected[other]:
            problems.append(
                f"{_describe(tree, test)} is allow-listed but has a twin in "
                f"tests/{other}/{file}"
            )
    return problems


HOW_TO_FIX = (
    "Port each test to the other tree under the same file, class and function "
    "name, or allow-list it in ALLOWED with the reason:"
)


def test_every_test_has_a_twin_in_the_other_tree():
    problems = unmatched({tree: collect(tree) for tree in TREES})
    assert not problems, "\n".join([HOW_TO_FIX, *problems])


def test_every_allowance_is_still_needed():
    problems = stale_allowances({tree: collect(tree) for tree in TREES})
    assert not problems, "\n".join(problems)
