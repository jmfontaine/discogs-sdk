# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. It is the one home for setup, the `just` recipes (every one of them,
with what it runs), the development workflow, testing (both integration recipes and the rate limit that keeps them
apart), code style and the pull request process. This file adds only what agents need beyond it: generator
directives, test-harness invariants, Discogs API quirks, releasing, and the git rules agents follow.

## Project Overview

A modern, typed Python SDK for the Discogs API. Supports both sync (`Discogs`) and async (`AsyncDiscogs`) clients with identical APIs. Built on httpx2 and Pydantic.

## Parallel Sessions

Never run `just test-integration` or `just test-unauthenticated` while other agent sessions work on this repository in
parallel: they share the same per-IP and per-token limits and would fail each other with 429. The default `just test`
mocks HTTP and is safe to run concurrently.

## Architecture

### Async-First, Generate Sync

`_sync/` is generated from `src/discogs_sdk/_async/` by `scripts/generate_sync.py`; the rule (edit only `_async/`,
then `just generate-sync`) is in [CONTRIBUTING.md](CONTRIBUTING.md#async-first-architecture).

The generator uses branch directives for code that differs between sync/async:
```python
if True:  # ASYNC
    await asyncio.sleep(delay)
else:
    time.sleep(delay)
```
The sync generator keeps only the `else` branch, or drops the whole statement when there is
no `else`. The `# ASYNC` comment must be on the `if True:` line; any other `if True:` under
`_async/` fails generation, and so does an `else`-less directive that is the only statement
in the body of a function, class or other compound statement. A failed run leaves `_sync/`
untouched.

String literals are copied verbatim, except `__all__` entries (renamed on an exact match) and
the literals listed in `REPR_RENAMES` inside a `__repr__` (today only `"<AsyncLazyResource "`).
Docstrings are shared by both clients: the generator renames async names on whole words,
rewrites code samples (literal blocks, doctest lines, inline literals) to sync syntax, and
rewords a few fixed phrases ("Async client", "an async", "async iterator"). Prose that still
says `async def`, `async with`, `async for` or `await` fails generation; word it so it holds
for both clients. Where the two clients need different prose (tasks against threads, say),
follow the docstring with an `ASYNC` directive whose `else` holds only the sync docstring:
```python
async def no_cache(self) -> AsyncGenerator[Self]:
    """Async docstring."""
    if True:  # ASYNC
        pass
    else:
        """Sync docstring."""
```
The sync code gets that docstring in place of the first one, checked and reworded the same way.
Such a directive anywhere other than directly after a docstring fails generation.

### Shared Base (`_base_client.py`)

All non-I/O client logic lives in `_base_client.py`: `BaseClient` holds URL building, header construction, auth and retry calculation; the module-level `raise_for_response` maps error statuses to exceptions for both clients and the OAuth helpers. Both client classes inherit from `BaseClient`.

### Lazy Loading

`.get(id)` returns a proxy object. No HTTP call happens until a data attribute is accessed. Sub-resource accessors (`.rating`, `.stats`, `.releases`) also never trigger HTTP. This minimizes API calls given Discogs' strict rate limits (60/min authenticated).

### Resource Pattern

Resources inherit from `AsyncAPIResource` (or `SyncAPIResource`), which provides `_get_list()`, `_post()`, `_put()`, `_delete()`, `_post_file()`, `_get_binary()`. A cacheable `GET` whose body the SDK parses passes a `parse` callable to `_send()` (as `_get_list()`, lazy proxies, the paginator and `user.identity()` do), so the body is validated before it is cached and on every cache hit.

API conventions: `.get(id)` for fetch, `.list()` for paginated lists, `.create()` for POST/PUT, `.update()` for POST, `.delete()` for DELETE.

Every caller-supplied value in a request path, `int` ids included, goes through `path_segment()` (`_base_client.py`), which percent-encodes it with `safe=""` and rejects `"."` and `".."`. Store the raw identifier on resources and proxies and encode where the path is built, so a chained sub-resource encodes it exactly once.

### Pagination

`.list()` returns auto-paging iterators (`AsyncPage`/`SyncPage`) that fetch pages on demand.

### Models

Pydantic `BaseModel` with `extra="allow"`. Uses `Literal` types over `Enum` for forward compatibility. Located in `src/discogs_sdk/models/`.

Every model derives from `SDKModel`, which keeps the mapping it was validated from in `raw`, so a normalized value
(a renamed key, a parsed timestamp) never hides what the API sent. Type a timestamp field as `Timestamp`
(`models/_timestamp.py`), never `str` or `datetime`; see "Timestamps Come in Several Shapes" below for what it
assumes.

### Auth

Three modes: personal token, consumer key/secret, OAuth 1.0a. Credentials resolve via: constructor arg > env var. OAuth helpers live in `src/discogs_sdk/oauth.py` (public API).

Env vars: `DISCOGS_TOKEN`, `DISCOGS_CONSUMER_KEY`, `DISCOGS_CONSUMER_SECRET`, `DISCOGS_ACCESS_TOKEN`, `DISCOGS_ACCESS_TOKEN_SECRET`.

### Error Hierarchy

`DiscogsError` > `DiscogsConnectionError` | `CacheMissError` | `CacheError` | `DiscogsAPIError` > `RateLimitError` | `NotFoundError` | `ForbiddenError` | `AuthenticationError` | `ValidationError`

## Test Harness

How to run the tests is in [CONTRIBUTING.md](CONTRIBUTING.md#testing). The invariants the harness enforces:

- HTTP mocking uses `respx` at the transport level via the `respx_mock` fixture, defined once in `tests/conftest.py`
  (routes relative to `BASE_URL`). It overrides the fixture respx's own pytest plugin provides, which patches only
  httpx/httpcore and has no `base_url`; never redefine it per file. A test that needs its own router, or one with
  `assert_all_called=False`, enters `mock_router(...)` from `tests/conftest.py` rather than calling `respx.mock`.
  Because the SDK runs on httpx2, every router must pass `using="httpcore2"` — respx's built-in mockers only patch
  httpx/httpcore and would silently intercept nothing — and `mock_router` is the one place that does. That mocker
  is registered by `pytest-httpx2` (respx's httpx2 companion, same author), which loads as a pytest plugin. Code
  outside pytest (an ad-hoc script, a REPL) must `import pytest_httpx2` before `respx.mock(using="httpcore2")`, or
  respx patches nothing and the requests reach the real API. Inside pytest, a session-scoped autouse fixture in
  `tests/conftest.py` aborts the run before the first test when the mocker is missing (plugin not installed, or
  disabled with `-p no:pytest_httpx2`)
- Build mocked responses with `respx.MockResponse(...)`, never `httpx2.Response(...)`: respx's `return_value` and
  `side_effect` guards hard-code `isinstance(..., httpx.Response)` and reject httpx2 responses outright
  ([respx#324](https://github.com/lundberg/respx/issues/324)). Exceptions are the opposite — `side_effect` must
  raise `httpx2.*` errors, since an `httpx.ConnectError` surfaces unchanged and escapes the SDK's handlers.
  Both rules carry a `KLUDGE:` in `tests/conftest.py` with the removal condition
- Shared payload factories in `tests/conftest.py` (`make_release()`, `make_artist()`, etc.)
- Async tests in `tests/async/`, sync tests in `tests/sync/` (both hand-maintained). Tests of shared, client-agnostic
  code (`BaseClient`, `build_oauth_header`, the exceptions) live once in `tests/`, not in both trees
- A test added to one tree needs a twin with the same file, class and function name in the other.
  `tests/test_sync_async_parity.py` fails on any test without one, unless its `ALLOWED` list exempts it with a
  reason (await-only behaviour, the tasks/threads pairs, tests of shared models). It also fails on an allow-list
  entry that is no longer needed
- `tests/test_examples_behavior.py` runs `examples/collection.py`, `marketplace.py`, `database.py` and
  `advanced.py` as scripts under a strict respx router and pins every request they send as
  `(method, path, body)`. Changing a request in one of them, or adding or dropping one, means updating
  its routes and expected sequence there
- `tests/test_doc_examples.py` runs every ` ```python ` block in README.md and `docs/**/*.md`, in order, one
  namespace per document (pre-seeded with `client = Discogs(token="test")`), under a strict respx router with
  home and the working directory in a temporary directory. `DOC_ROUTES` there lists the routes each document's
  examples request; register a route only for a request an example actually sends (an unread lazy proxy sends
  none). A failure names the file and line. Skip a block only with `<!-- doc-test: skip (reason) -->` on the line
  right before its fence
- `pytest-asyncio` with `asyncio_mode="auto"` — no need for `@pytest.mark.asyncio`
- Integration tests marked with `@pytest.mark.integration`, excluded by default
- `.github/workflows/integration.yml` runs the live suite weekly (and on manual dispatch) in two
  jobs: one authenticated with the repository secrets, one with no credentials at all. A scheduled
  failure opens (or comments on) an issue labelled `integration-failure` that names each failed job
  and step. GitHub disables cron workflows after 60 days without repository activity, so re-enable
  it if the repo goes quiet
- The live suite never resets the account. Each writing test removes what it created in a `finally` block, and
  tags everything it creates (`TEST_FOLDER_PREFIX`, `WANT_MARKER`) so the *next* run reclaims what a killed run left;
  writes stay in the suite's own scratch folder, never folder 1 (Uncategorized). An untagged want is the owner's and
  is never touched. How the sweep, the tagging and the one uncovered window work is documented in
  `tests/integration/conftest.py` and `tests/integration/test_wantlist.py`. `tests/test_integration_safety.py` runs
  those flows against mocks to prove nothing else is deleted
- To stub `eventually()`, patch the `time` name in `tests/integration/conftest.py`, as the autouse fixture in
  `tests/test_integration_safety.py` does, never `time.sleep` by dotted path: that replaces the function
  process-wide, the SDK's own retry sleeps included

## Design Decisions

The "Design principles" section of README.md states what the SDK may normalize, which calls it may combine, and
that it never invents data or depends on undocumented API behaviour outside `discogs_sdk.experimental`. Check every
new feature against it. A helper in `experimental` (async source in `_async/_experimental.py`, shared result types in
`_experimental_types.py`) is reached only through that module, never exported from `__init__.py`, and its docstring
links the principles section.

### Field Aliases

Where the Discogs API uses inconsistent or cryptic field names (`uri150`, `anv`, `catno`, `extraartists`, etc.), models use clean Python names with `Field(validation_alias="api_name")`. Both names work for deserialization; attribute access uses the Python name. See the "Field naming" table in `docs/models.md`.

### No Auto-Expansion of Embedded Objects

Embedded objects like `SubLabel`, `ArtistCredit`, and `LabelCredit` stay minimal — they contain only what the API returns inline. They do **not** auto-fetch the full resource. This is deliberate: hidden HTTP calls are dangerous given the 60/min rate limit. Users who need the full object use `client.labels.get(sublabel.id)` explicitly, which is consistent with the SDK's lazy-loading contract (no HTTP until you ask for it).

## User Docs

- The user guide lives in `docs/`, one page per topic, indexed by `docs/README.md`. README.md keeps the pitch,
  features, comparison, installation, a short quick start, the design principles and a "Documentation" section
  linking every page. The two indexes list the same pages, in the same order, with the same descriptions;
  `tests/test_doc_consistency.py` fails when they differ
- Each rule a caller must know (lazy loading, async proxies, pagination cost, retries, writes, caching, field names)
  is stated in full once, under "Behaviors to know" in `docs/getting-started.md`. README.md's "Behaviors to know"
  keeps one sentence per rule linking there, and the skill's rules keep the actionable instruction and link its
  `references/`. The rules snippet in `docs/ai-agents.md` and the `rules` in `context7.json` are short hand-written
  lists: every item of each must carry the key phrases of exactly one rule in `RULES` in
  `tests/test_doc_consistency.py`, and every rule there must appear in both. Add or drop a rule in both lists and in
  `RULES` together
- Pages render on GitHub as plain Markdown: CommonMark plus GitHub alerts (`> [!NOTE]`), no docs generator and no
  generator-specific syntax. Pages link to each other relatively; README.md links to them by absolute URL
- `tests/test_doc_links.py` checks without network I/O that every local link in README.md, `docs/`, the packaged
  skill, AGENTS.md and CONTRIBUTING.md (and every absolute `blob/main/` or `tree/main/` URL into this repository, plus
  `blob/v<project.version>/` for a release version) names an existing file and, with a `#fragment`, an existing
  heading. Moving a section means rewriting the links into it
- Examples use Nine Inch Nails data and show both clients wherever their behaviour differs
- Every Python block is executed by `tests/test_doc_examples.py`, one namespace per page; a page sets up its own
  `client` rather than relying on one from another page
- The vendored API reference lives in `reference/discogs_api/`, never under `docs/`
- `context7.json` tells [Context7](https://context7.com) to index README.md and `docs/` only, and its `rules` tell
  agents which library this is. `excludeFiles` replaces Context7's default list, so keep the defaults in it. Each rule
  is at most 255 characters. Validate a change with
  `uvx check-jsonschema --schemafile https://context7.com/schema/context7.json context7.json`
- The package ships an agent skill (the [library-skills](https://library-skills.io/create/) convention) at
  `src/discogs_sdk/.agents/skills/discogs-sdk/`. `SKILL.md` is hand-written and its Python blocks run in
  `tests/test_doc_examples.py`. `references/` is generated by `just generate-skill-refs` from the docs pages listed in
  `PAGES` in `scripts/generate_skill_refs.py`: never edit it by hand. Regenerate after editing one of those pages and
  after every version bump (the release recipes do it), since links into the other pages are pinned to
  `v<project.version>` for a release version and to `main` for a development one; `just qa` and the CI
  quality job check them (the `skill-refs-check` hook). The generator rewrites only bare inline links
  (`[text](target)`), so copied pages use no other link form. A new reference goes in `PAGES` and gets a line in
  `SKILL.md`; the release checks (`scripts/check_distributions.py`, `scripts/check_installed_package.py`) build their
  file lists from `PAGES`

## Discogs API Documentation

The official Discogs API documentation is available locally in `reference/discogs_api/` as Markdown files. This directory is git-ignored for copyright reasons, and it sits outside `docs/` so that a docs build pointed at `docs/` can never pick it up. Use these files as a reference when implementing or verifying API endpoints, request/response shapes, and query parameters.

Refresh it with `just update-api-docs` (`scripts/update_api_docs.py`), which fetches
the official reference and reports drift. Because the directory is git-ignored, an
overwrite is irreversible, so writing is opt-in: the default run and `--check` only
report, `--diff` prints the unified diffs, and `--write` is required to replace the
local files. After a refresh, `just endpoints-coverage` checks the new examples against `tests/documented_payloads.py`
([CONTRIBUTING.md](CONTRIBUTING.md#endpoint-coverage)).

## Discogs API Quirks

### Rate Limits

- Authenticated: 60 requests/min. Unauthenticated: 25 requests/min.
- Rate limit window is a moving average over 60 seconds; resets after 60 seconds of inactivity.
- The SDK retries reads on 429 using the standard `Retry-After` header (seconds or HTTP-date). A valid value above
  `MAX_RETRY_AFTER` (60s, not configurable) is never slept through: the error is raised at once. Invalid values
  (negative, `nan`, `inf`, garbage) fall back to exponential backoff.
- `client.ratelimit` exposes the `X-Discogs-Ratelimit*` headers; `on_request` emits a `RequestEvent` per request.

### User-Agent Required

The Discogs API silently returns empty responses if no `User-Agent` header is sent. The SDK sets one automatically.

### Auth Capability Matrix

| Credentials | Rate limit | Image URLs | User-scoped access |
|---|---|---|---|
| None | 25/min | Resource reads only | No |
| Consumer key/secret only | 60/min | Yes | No |
| Personal token | 60/min | Yes | Yes (token holder only) |
| Full OAuth | 60/min | Yes | Yes (any authorized user) |

Consumer key/secret alone does **not** grant access to user-specific resources (marketplace orders, private collections, wantlists). Only a token or full OAuth does.

Without credentials, `GET /releases/{id}` returns the full `images` array, while search results come back with empty
`cover_image` and `thumb` strings. `tests/integration/test_unauthenticated.py` pins both sides.

### Search Is Open to Anonymous Clients

`/database/search` answers anonymous requests, minus the image fields above. The scheduled integration workflow covers
it.

### Collection Folder Semantics

- Folder 0 = "All" (read-only, cannot add releases to it)
- Folder 1 = "Uncategorized" (default destination)
- Folders 0 and 1 cannot be renamed or deleted
- Custom folders must be empty before deletion

### Adding a Want Takes Nothing but the Release ID

`PUT /users/{u}/wants/{release_id}` discards the `notes` and `rating` it documents, while `POST` on the same path
(`wantlist.update()`) stores them, so `Wantlist.create()` takes only `release_id`. The evidence is in its docstring
(`_async/resources/wantlist.py`).

### Writes Are Not Read-Your-Own

A successful write, deletes included, is not immediately visible to the next read, so anything that reads one back
has to poll. The measured lag and the polling helper are in `eventually()` (`tests/integration/conftest.py`).

### Timestamps Come in Several Shapes, Some Without an Offset

`Timestamp` makes each timestamp field an aware `datetime`, reads a
value sent without an offset as `America/Los_Angeles` time, and stores the fixed offset in force then, never a
`ZoneInfo`. That zone is an **assumption** Discogs does not document: the measurements behind it, and when to
revisit it, are in the header of `models/_timestamp.py`. `docs/models.md` describes the behaviour for users.

### Marketplace Listing Edit Restrictions

Only listings with status `For Sale`, `Draft`, or `Expired` can be modified. Sold listings cannot be edited — they must be re-created as new listings.

### 403 Mapped to ForbiddenError

Authenticated requests that lack permission (e.g., accessing another user's private collection) raise `ForbiddenError`.

## Releasing

Publishing is fully automated via CI. The `publish.yml` workflow triggers on `v*` tag push.

Between releases, `main` carries a PEP 440 development version, `X.Y.Z.devN`, which sorts below `X.Y.Z`, so a build
from `main` never passes for the release. The version changes only through the recipes below, each from an up-to-date,
clean `main` (they fetch `origin/main` and refuse to go on unless `HEAD` is that commit and the tree is clean). The two
that change the version create a `release/v<version>` branch, set the version in `pyproject.toml` and `uv.lock`,
regenerate the skill references, commit, push and open the pull request.

1. Run `just release-prepare`. It sets the release version, `X.Y.Z.devN` minus its `.devN`; pass another `X.Y.Z` to
   release that instead (`just release-prepare 0.8.2` for a patch while `main` is on `0.9.0.dev0`). The references'
   links now name the `vX.Y.Z` tag. Merging the pull request (squash) is the go/no-go point
2. Run `git checkout main && git pull --ff-only`, then `just release`. It refuses any version but a plain `X.Y.Z`
   and an existing tag, then creates a signed tag, pushes only the tag, and monitors the workflow
3. Run `just release-next`, which refuses unless the `vX.Y.Z` tag is on `origin`. It sets the next minor development
   version, `X.(Y+1).0.dev0` (`just release-next patch` or `major` for the others), and the references' links name
   `main` again. Squash-merge the pull request

The workflow's first job, the tag guard, fails the run before anything is built unless the tag minus its `v` equals
`project.version` in `pyproject.toml` and the tagged commit is an ancestor of `origin/main`, so a tag pushed by hand
from anywhere else publishes nothing.

The push is the point of no return: once the tag exists, the recipe refuses to run again. If it fails after pushing,
do not rerun it; it says how to find the publish run (the justfile recipe describes its polling).

The workflow builds the distributions once and publishes those exact files. Before upload it runs every job in
ci.yml, by calling that workflow: QA, the test matrix, the tests against the declared dependency floors (`lowest`),
`scripts/check_distributions.py` (archive contents) and `twine check --strict` (metadata), then installs the built
wheel into a clean environment on the oldest and newest supported Python and runs the whole test suite against it,
and installs the sdist on the newest. Publishing uses PyPI Trusted Publishers (OIDC); the `pypi` GitHub environment
must exist on the repo.

A release cannot be replaced once uploaded. If a broken version reaches PyPI, yank it there (project
page or the upload API — there is no `pip yank`), then release the fix as the next patch:
`just release-prepare X.Y.(Z+1)` once `main` is on a development version, or `just release-next patch` first if it is
still on `X.Y.Z`.

## Key Conventions

- `.python-version` pins an exact CPython release (`3.13.16`). Local `uv run` and every single-version CI job
  (quality, build, integration) read it; only the test matrices float. `generate_sync.py` output
  depends on the patch release, since `ast.unparse` changes between them, so bump the file deliberately and
  run `just generate-sync` in the same commit
- Workarounds that are knowingly less than ideal carry a `KLUDGE:` comment stating what is wrong and what
  removes it. Grep for `KLUDGE` to find them; do not add one without a removal condition
- `pyproject.toml` requires `pydantic>=2.14` on every Python: 2.14 is the first release with Python 3.15 wheels.
  Keep pydantic a single entry: a second, marker-scoped one makes Dependabot rewrite the first and break the lock
  (the comment there links the upstream bug)
- Dead-code analysis runs through `scripts/check_dead_code.sh`, which pins the tool and its interpreter;
  every caller (the `dead-code` recipe and the pre-commit hook) invokes that script rather than `deadcode` directly
- `.pre-commit-config.yaml` is the one list of fast checks: the git hooks, `just qa` and the CI quality job all run
  it, so a new check goes there as a hook. Python tools run as `local` hooks through `uv run`, so `uv.lock` is their
  only version source (except dead code, pinned by its script); Dependabot's `uv` updates and `just deps-update` move
  them
- Every `uses:` in `.github/workflows/` names a full commit SHA followed by its release tag as a comment
  (`actions/checkout@<sha> # v7.0.1`); Dependabot's `github-actions` updates rewrite both. Pin a new action the
  same way, to the SHA of a version tag, never a branch
- CI installs with `uv sync --locked` and exports the wheel jobs' test stack with `uv export --locked`, so a
  `pyproject.toml` dependency change without `uv lock` in the same commit fails the build. Only the `lowest` job
  re-resolves, on purpose (`--resolution lowest-direct`)
- Pushing a change under `.github/workflows/` needs the `workflow` scope on the `gh` token: agent sessions
  push over HTTPS through `gh auth git-credential`, even though `origin` is an SSH URL, and GitHub rejects such a
  push without that scope. `gh auth status` lists the scopes; `gh auth refresh -h github.com -s workflow` adds it
- All public API exports go through `src/discogs_sdk/__init__.py`
- How to add a resource or a model is in [CONTRIBUTING.md](CONTRIBUTING.md#adding-a-new-resource)
- `py.typed` marker present (PEP 561) — the package is typed
- `examples/` contains runnable usage examples: `quickstart.py`, `authentication.py`, `database.py`, `collection.py`,
  `marketplace.py`, `advanced.py` and `async_usage.py`
- All examples in docs, README, docstrings, and `examples/` must use Nine Inch Nails related data (artist 3857, release 352665, master 3719, label 647 Nothing Records, etc.)
- README.md is the PyPI long description, and PyPI leaves relative links broken, so every link and image in it is
  absolute (`https://github.com/jmfontaine/discogs-sdk/blob/main/<path>`, `tree/main/<dir>` for a directory) or an
  in-page anchor. `tests/test_doc_links.py` fails on any other target
- Run `git` commands directly, never with `git -C`
- Never commit on `main`. Work starts on a branch named as [CONTRIBUTING.md](CONTRIBUTING.md#submitting-a-pull-request)
  describes; a version bump goes on `release/v<version>`, created by the [release recipes](#releasing). Either way it
  lands through a pull request
- Finished work is committed, pushed and opened as a pull request without asking first.
  Stop for input only when a decision needs the user
- `main` rejects force pushes and deletion (ruleset "Protect default branch") and takes only squash merges of signed,
  verified commits ([CONTRIBUTING.md](CONTRIBUTING.md#what-to-expect)). Merge with `gh pr merge <n> --squash`, or, for
  a stack, `gh stack merge --yes --squash` run with no number from a worktree that has the stack checked out (a bare
  number is read as a stack number before a pull request number)
- `CI passed`, the `ci-passed` job in `.github/workflows/ci.yml`, is the only required status check. It needs every
  other job in that workflow, so a job added there must be added to its `needs`; no ruleset change is required

## Shared workflow

This repository follows the shared workflow: the `github-workflow` skill's repository
setup describes its GitHub settings, rulesets, labels and templates. Those settings are
managed as code outside this repository; change them there, never with `gh api` or the
GitHub web UI.

### Deviations from the shared workflow

- **Extra label `integration-failure`.** The scheduled live-API workflow opens or
  comments on an issue with it, so failures stay visible without anyone relaying them.
