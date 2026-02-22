# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A modern, typed Python SDK for the Discogs API. Supports both sync (`Discogs`) and async (`AsyncDiscogs`) clients with identical APIs. Built on httpx and Pydantic.

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
just dead-code          # deadcode src tests examples
just deps-unused        # deptry src
just deps-update        # Update deps to latest versions
just test-integration   # Run integration tests (requires DISCOGS_TOKEN)
just verify-types       # Audit public API type annotation coverage (informational, not a gate)
just verify-oauth       # Verify OAuth flow interactively
just release            # Tag, push, and monitor the publish workflow
just pre-commit         # Run pre-commit hooks on all files
just pre-commit-install # Install pre-commit hooks
just pre-commit-update  # Update pre-commit hooks to latest versions
```

Run a single test: `uv run pytest tests/async/test_releases.py -k test_get_release`

Generate sync code from async sources: `uv run python scripts/generate_sync.py`
Check sync staleness: `uv run python scripts/generate_sync.py --check`

Integration tests require `DISCOGS_TOKEN`: `just test-integration`

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

- HTTP mocking uses `respx` at the transport level via `respx_mock` fixture
- Shared payload factories in `tests/conftest.py` (`make_release()`, `make_artist()`, etc.)
- Async tests in `tests/async/`, sync tests in `tests/sync/` (both hand-maintained)
- `pytest-asyncio` with `asyncio_mode="auto"` — no need for `@pytest.mark.asyncio`
- Integration tests marked with `@pytest.mark.integration`, excluded by default

## Design Decisions

### Field Aliases

Where the Discogs API uses inconsistent or cryptic field names (`uri150`, `anv`, `catno`, `extraartists`, etc.), models use clean Python names with `Field(validation_alias="api_name")`. Both names work for deserialization; attribute access uses the Python name. See the "Field naming" table in README.md.

### No Auto-Expansion of Embedded Objects

Embedded objects like `SubLabel`, `ArtistCredit`, and `LabelCredit` stay minimal — they contain only what the API returns inline. They do **not** auto-fetch the full resource. This is deliberate: hidden HTTP calls are dangerous given the 60/min rate limit. Users who need the full object use `client.labels.get(sublabel.id)` explicitly, which is consistent with the SDK's lazy-loading contract (no HTTP until you ask for it).

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
| None | 25/min | No | No |
| Consumer key/secret only | 60/min | Yes | No |
| Personal token | 60/min | Yes | Yes (token holder only) |
| Full OAuth | 60/min | Yes | Yes (any authorized user) |

Consumer key/secret alone does **not** grant access to user-specific resources (marketplace orders, private collections, wantlists). Only a token or full OAuth does.

### Search Requires Authentication

`/database/search` requires authentication (any mode). Unauthenticated search returns 401.

### Collection Folder Semantics

- Folder 0 = "All" (read-only, cannot add releases to it)
- Folder 1 = "Uncategorized" (default destination)
- Folders 0 and 1 cannot be renamed or deleted
- Custom folders must be empty before deletion

### Marketplace Listing Edit Restrictions

Only listings with status `For Sale`, `Draft`, or `Expired` can be modified. Sold listings cannot be edited — they must be re-created as new listings.

### 403 Mapped to ForbiddenError

Authenticated requests that lack permission (e.g., accessing another user's private collection) raise `ForbiddenError`.

## Releasing

Publishing is fully automated via CI. The `publish.yml` workflow triggers on `v*` tag push.

1. Update `version` in `pyproject.toml`
2. Commit the version bump
3. Run `just release` — creates a signed tag, pushes, and monitors the workflow

The workflow runs QA + tests, publishes to PyPI via Trusted Publishers (OIDC), and creates a GitHub release with auto-generated notes. The `pypi` GitHub environment must exist on the repo.

## Key Conventions

- Python 3.10+ required, ruff targets 3.14, line length 120
- All public API exports go through `src/discogs_sdk/__init__.py`
- New resources: add to `_async/resources/`, wire into `_async/_client.py`, export from `__init__.py`, then regenerate sync
- New models: add to `models/`, export from `models/__init__.py` and `__init__.py`
- `py.typed` marker present (PEP 561) — the package is typed
- `examples/` contains runnable usage examples (quickstart, auth, database, collection, marketplace, async)
- All examples in docs, README, docstrings, and `examples/` must use Nine Inch Nails related data (artist 3857, release 352665, master 3719, label 647 Nothing Records, etc.)
- Run `git` commands directly, never with `git -C`
