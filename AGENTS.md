# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.

## Project Overview

A modern, typed Python SDK for the Discogs API. Supports both sync (`Discogs`) and async (`AsyncDiscogs`) clients with identical APIs. Built on httpx2 and Pydantic.

## Commands

Task runner is `just`. All commands use `uv run` under the hood.

```bash
just setup              # Install deps + pre-commit hooks
just test               # Run pytest with coverage (excludes integration tests)
just test <path>        # Run specific test file or directory
just qa                 # All checks: dead-code, deps-unused, format-check, lint, sync-check, type-check
just lint               # ruff check
just lint-fix           # ruff check --fix
just format             # ruff format + pyproject-fmt
just type-check         # ty check
just generate-sync      # Generate _sync/ from _async/ sources
just sync-check         # Check _sync/ is up to date with _async/
just dead-code          # deadcode src tests examples (run via uvx under Python 3.13)
just deps-unused        # deptry src
just deps-update        # Update deps to latest versions
just test-integration   # Run authenticated integration tests (requires DISCOGS_TOKEN)
just test-unauthenticated # Run credential-free integration tests
just verify-types       # Audit public API type annotation coverage (informational, not a gate)
just verify-oauth       # Verify OAuth flow interactively
just update-api-docs    # Compare docs/discogs_api/ with the official reference (writes only with --write)
just release            # Tag, push, and monitor the publish workflow
just pre-commit         # Run pre-commit hooks on all files
just pre-commit-install # Install pre-commit hooks
just pre-commit-update  # Update pre-commit hooks to latest versions
```

Run a single test: `uv run pytest tests/async/test_releases.py -k test_get_release`

Generate sync code from async sources: `uv run python scripts/generate_sync.py`
Check sync staleness: `uv run python scripts/generate_sync.py --check`

`just test-integration` needs `DISCOGS_TOKEN`; `just test-unauthenticated` needs nothing.
Keep them apart: the anonymous 25/min limit is per IP and the authenticated calls
consume it, so running both within a minute makes the anonymous ones fail with 429.

## Architecture

### Async-First, Generate Sync

`src/discogs_sdk/_async/` is the **source of truth**. `_sync/` is auto-generated via AST transformation (`scripts/generate_sync.py`). Never edit `_sync/` files directly.

The generator uses branch directives for code that differs between sync/async:
```python
if True:  # ASYNC
    await asyncio.sleep(delay)
else:
    time.sleep(delay)
```
The sync generator keeps only the `else` branch.

### Shared Base (`_base_client.py`)

All non-I/O logic lives in `BaseClient`: URL building, header construction, auth, retry calculation, error mapping. Both client classes inherit from it.

### Lazy Loading

`.get(id)` returns a proxy object. No HTTP call happens until a data attribute is accessed. Sub-resource accessors (`.rating`, `.stats`, `.releases`) also never trigger HTTP. This minimizes API calls given Discogs' strict rate limits (60/min authenticated).

### Resource Pattern

Resources inherit from `AsyncAPIResource` (or `SyncAPIResource`), which provides `_get()`, `_post()`, `_put()`, `_delete()`, `_post_file()`, `_get_binary()`.

API conventions: `.get(id)` for fetch, `.list()` for paginated lists, `.create()` for POST/PUT, `.update()` for POST, `.delete()` for DELETE.

### Pagination

`.list()` returns auto-paging iterators (`AsyncPage`/`SyncPage`) that fetch pages on demand.

### Models

Pydantic `BaseModel` with `extra="allow"`. Uses `Literal` types over `Enum` for forward compatibility. Located in `src/discogs_sdk/models/`.

### Auth

Three modes: personal token, consumer key/secret, OAuth 1.0a. Credentials resolve via: constructor arg > env var. OAuth helpers live in `src/discogs_sdk/oauth.py` (public API).

Env vars: `DISCOGS_TOKEN`, `DISCOGS_CONSUMER_KEY`, `DISCOGS_CONSUMER_SECRET`, `DISCOGS_ACCESS_TOKEN`, `DISCOGS_ACCESS_TOKEN_SECRET`.

### Error Hierarchy

`DiscogsError` > `DiscogsConnectionError` | `DiscogsAPIError` > `RateLimitError` | `NotFoundError` | `ForbiddenError` | `AuthenticationError` | `ValidationError`

## Testing

- HTTP mocking uses `respx` at the transport level via `respx_mock` fixture. Because the SDK runs on httpx2,
  every `respx.mock(...)` call must pass `using="httpcore2"` — respx's built-in mockers only patch httpx/httpcore
  and would silently intercept nothing. That mocker is registered by `pytest-httpx2` (respx's httpx2 companion,
  same author), which loads as a pytest plugin
- Build mocked responses with `respx.MockResponse(...)`, never `httpx2.Response(...)`: respx's `return_value` and
  `side_effect` guards hard-code `isinstance(..., httpx.Response)` and reject httpx2 responses outright
  ([respx#324](https://github.com/lundberg/respx/issues/324)). Exceptions are the opposite — `side_effect` must
  raise `httpx2.*` errors, since an `httpx.ConnectError` surfaces unchanged and escapes the SDK's handlers.
  Both rules carry a `KLUDGE:` in `tests/conftest.py` with the removal condition
- Shared payload factories in `tests/conftest.py` (`make_release()`, `make_artist()`, etc.)
- Async tests in `tests/async/`, sync tests in `tests/sync/` (both hand-maintained)
- `pytest-asyncio` with `asyncio_mode="auto"` — no need for `@pytest.mark.asyncio`
- Integration tests marked with `@pytest.mark.integration`, excluded by default
- `.github/workflows/integration.yml` runs the live suite weekly (and on manual dispatch) in two
  jobs: one authenticated with the repository secrets, one with no credentials at all. A scheduled
  failure opens (or comments on) an issue labelled `integration-failure`. GitHub disables cron
  workflows after 60 days without repository activity, so re-enable it if the repo goes quiet
- The live suite never resets the account. Each writing test removes what it created in a `finally`
  block, and everything it creates is tagged so the *next* run can reclaim what a killed run left:
  collection folders are named with `TEST_FOLDER_PREFIX` and swept by the `scratch_folder` fixture,
  and the wantlist entry carries `WANT_MARKER` in its notes, applied by a follow-up `update()` since
  the create endpoint discards notes. An untagged want is treated as the owner's: `unavailable()`
  skips locally and *fails* under `GITHUB_ACTIONS`, so the scheduled job cannot go green on a test
  that never ran. (`CI` is unusable for that check — dev shells set it.) Writes stay inside the
  suite's own scratch folder, never folder 1 (Uncategorized), so a leftover is always
  distinguishable from a real copy. One window is not covered: a run killed between the want's
  create and its tagging `update()` leaves an untagged entry that no later run will claim.
  `tests/test_integration_safety.py` runs those flows and the sweep against mocks to prove nothing
  else is deleted

## Design Decisions

### Field Aliases

Where the Discogs API uses inconsistent or cryptic field names (`uri150`, `anv`, `catno`, `extraartists`, etc.), models use clean Python names with `Field(validation_alias="api_name")`. Both names work for deserialization; attribute access uses the Python name. See the "Field naming" table in README.md.

### No Auto-Expansion of Embedded Objects

Embedded objects like `SubLabel`, `ArtistCredit`, and `LabelCredit` stay minimal — they contain only what the API returns inline. They do **not** auto-fetch the full resource. This is deliberate: hidden HTTP calls are dangerous given the 60/min rate limit. Users who need the full object use `client.labels.get(sublabel.id)` explicitly, which is consistent with the SDK's lazy-loading contract (no HTTP until you ask for it).

## Discogs API Documentation

The official Discogs API documentation is available locally in `docs/discogs_api/` as Markdown files. This directory is git-ignored for copyright reasons. Use these files as a reference when implementing or verifying API endpoints, request/response shapes, and query parameters.

Refresh it with `just update-api-docs` (`scripts/update_api_docs.py`), which fetches
the official reference and reports drift. Because the directory is git-ignored, an
overwrite is irreversible, so writing is opt-in: the default run and `--check` only
report, `--diff` prints the unified diffs, and `--write` is required to replace the
local files.

## Discogs API Quirks

### Rate Limits

- Authenticated: 60 requests/min. Unauthenticated: 25 requests/min.
- Rate limit window is a moving average over 60 seconds; resets after 60 seconds of inactivity.
- The SDK retries on 429 using the standard `Retry-After` header.

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

Image URLs used to require credentials everywhere. As of 2026-09 an anonymous `GET /releases/{id}` returns the full `images` array; only search results are stripped, coming back with empty `cover_image` and `thumb` strings. `tests/integration/test_unauthenticated.py` pins the current behaviour on both sides.

### Search Is Open to Anonymous Clients

`/database/search` used to return 401 without credentials. As of 2026-09 it answers anonymous requests normally, minus the image fields above. Both halves are covered by the scheduled integration workflow.

### Collection Folder Semantics

- Folder 0 = "All" (read-only, cannot add releases to it)
- Folder 1 = "Uncategorized" (default destination)
- Folders 0 and 1 cannot be renamed or deleted
- Custom folders must be empty before deletion

### Adding a Want Takes Nothing but the Release ID

`PUT /users/{u}/wants/{release_id}` documents `notes` and `rating` and discards both — verified
2026-09-13 as a JSON body and as query parameters; the response and every later read return `""`
and `0`, and the reference's own PUT example shows `"notes": ""`. `POST` on the same path (i.e.
`wantlist.update()`) stores them. `Wantlist.create()` therefore takes only `release_id`.

### Writes Are Not Read-Your-Own

A successful write is not immediately visible to the next read. Measured 2026-09-13: a want that
`PUT` had acknowledged was still missing from `GET /users/{u}/wants` after 17s and present after
37s; deletes lag the same way. Anything that reads back a write has to poll (see `eventually()` in
`tests/integration/conftest.py`).

### Marketplace Listing Edit Restrictions

Only listings with status `For Sale`, `Draft`, or `Expired` can be modified. Sold listings cannot be edited — they must be re-created as new listings.

### 403 Mapped to ForbiddenError

Authenticated requests that lack permission (e.g., accessing another user's private collection) raise `ForbiddenError`.

## Releasing

Publishing is fully automated via CI. The `publish.yml` workflow triggers on `v*` tag push.

1. Update `version` in `pyproject.toml`
2. Commit the version bump
3. Run `just release` — creates a signed tag, pushes, and monitors the workflow

The workflow builds the distributions once and publishes those exact files. Before upload it runs QA,
the test matrix, `scripts/check_distributions.py` (archive contents) and `twine check --strict`
(metadata), then installs the built wheel into a clean environment on the oldest and newest supported
Python and runs the whole test suite against it, and installs the sdist on the newest. Publishing uses
PyPI Trusted Publishers (OIDC); the `pypi` GitHub environment must exist on the repo.

A release cannot be replaced once uploaded. If a broken version reaches PyPI, yank it there (project
page or the upload API — there is no `pip yank`), then bump the patch version and release again.

## Key Conventions

- Python 3.10+ required (CI tests through 3.15), ruff targets 3.10 to match `requires-python`, line length 88
- Workarounds that are knowingly less than ideal carry a `KLUDGE:` comment stating what is wrong and what
  removes it. Grep for `KLUDGE` to find them; do not add one without a removal condition
- Python 3.15 needs `pydantic>=2.14.0b2` (earlier pins lack cp315 wheels), declared in `pyproject.toml`
  with markers whose exact form matters — read the comment there before touching it. `uv.lock` forks
  pydantic and pydantic-core as a result, so expect two entries for each
- Dead-code analysis runs through `scripts/check_dead_code.sh`, which pins the tool and its interpreter;
  every caller (justfile, pre-commit, both workflows) invokes that script rather than `deadcode` directly
- All public API exports go through `src/discogs_sdk/__init__.py`
- New resources: add to `_async/resources/`, wire into `_async/_client.py`, export from `__init__.py`, then regenerate sync
- New models: add to `models/`, export from `models/__init__.py` and `__init__.py`
- `py.typed` marker present (PEP 561) — the package is typed
- `examples/` contains runnable usage examples (quickstart, auth, database, collection, marketplace, async)
- All examples in docs, README, docstrings, and `examples/` must use Nine Inch Nails related data (artist 3857, release 352665, master 3719, label 647 Nothing Records, etc.)
- Run `git` commands directly, never with `git -C`
