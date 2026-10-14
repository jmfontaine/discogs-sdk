# Contributing to discogs-sdk

Contributions are welcome — bug fixes, new features, documentation, test coverage.
This guide walks you through the development setup and PR process.

For larger changes, please open an issue first so we can discuss the approach
before you invest significant time.

## Reporting bugs and requesting features

Before opening an issue, search [existing issues](https://github.com/jmfontaine/discogs-sdk/issues) to avoid duplicates.

**Bug reports** should include:
- Python version and discogs-sdk version (`python --version`, `pip show discogs-sdk` or `uv pip show discogs-sdk`)
- Minimal code example that reproduces the issue
- Full traceback or error message

**Feature requests** — describe the problem you want to solve, not just the solution.
For new API resource coverage, note which Discogs API endpoints are involved.

A new feature, and any change to what the SDK sends or returns, must follow the
[design principles](README.md#design-principles): predictable requests, lossless and documented normalization, no
invented data, no default caps, and undocumented API behaviour kept out of the core.

## Setup

```bash
git clone https://github.com/jmfontaine/discogs-sdk.git
cd discogs-sdk
just setup
cp .env.example .env
```

`just setup` needs only [uv](https://docs.astral.sh/uv/) and
[just](https://github.com/casey/just) on your PATH. It installs every dependency — including pre-commit, which is
declared in the `dev` dependency group — and then installs the git hooks. Every recipe invokes pre-commit through
`uv run`, so no global installation is required.

`.env` holds the credentials the [integration tests](#integration-tests) read; its values can stay empty until you run
them. If you use [direnv](https://direnv.net/), `.envrc` loads `.env` whenever it exists: run `direnv allow` once.

> [!TIP]
> The task runner is [just](https://github.com/casey/just). If you don't have it installed, you can run the underlying
> commands directly. Check [`justfile`](justfile) to see what each recipe runs — most are one-line `uv run` commands.
> For example, `just test` runs `uv run pytest --cov`.

## Commands

Every recipe, as `just --list` shows them:

```bash
# Everyday
just test                  # Unit tests with coverage (fast, no network)
just qa                    # All checks: every pre-commit hook on all files, then verify-types
just format                # Run the formatters (pyproject-fmt, ruff format)
just lint-fix              # Fix lint issues (ruff check --fix)

# One check at a time (each also runs in just qa)
just dead-code             # Find dead code (deadcode, pinned in scripts/check_dead_code.sh)
just deps-unused           # Check for unused or undeclared dependencies (deptry)
just endpoints-check       # Check docs/endpoints.md is up to date with the SDK sources
just format-check          # Check formatting without modifying files
just lint                  # Run the linter (ruff check)
just skill-refs-check      # Check the agent skill's references/ match the docs pages they copy
just sync-check            # Check _sync/ is up to date with _async/
just type-check            # Run the type checker (ty)
just verify-types          # Audit public API type completeness; fails below 100%

# Generators
just generate-sync         # Generate _sync/ from _async/
just generate-endpoints    # Generate docs/endpoints.md from the SDK sources, then its copy in the skill's references/
just generate-skill-refs   # Copy docs pages into the agent skill's references/

# Against the git-ignored API reference copy in reference/discogs_api/ (never run in CI)
just endpoints-coverage    # Check the SDK's routes and the documented payloads against reference/discogs_api/
just update-api-docs       # Compare reference/discogs_api/ with the official reference (--diff, --check, --write)

# Against the live Discogs API (not part of pull request CI)
just test-integration      # Authenticated integration tests (needs DISCOGS_TOKEN)
just test-unauthenticated  # Integration tests that use no credentials
just verify-oauth          # Walk through the OAuth flow interactively

# Maintenance
just setup                 # Install dependencies and the git hooks
just deps-update           # Upgrade uv.lock to the latest versions and sync
just pre-commit            # Run every pre-commit hook on all files
just pre-commit-install    # Install the git hooks
just pre-commit-update     # Update the remote pre-commit hooks (the local ones use the uv.lock versions)
just changelog-preview     # Preview release notes for unreleased changes
just release               # Maintainers only: tag the merged origin/main and publish it
```

`just qa` runs every hook in `.pre-commit-config.yaml` against all files, then `just verify-types` (the
type-completeness audit of the whole package, which is not a hook). The CI quality job runs the same two. Hooks that
fix files (ruff, pyproject-fmt, whitespace) apply their fixes and fail, so run `just qa` again after reviewing what
they changed.

`just release` follows the release steps in [AGENTS.md](AGENTS.md#releasing).

## Development workflow

### Async-first architecture

> [!WARNING]
> `_sync/` source files are auto-generated from `_async/` via AST transformation.
> Never edit them directly — your changes will be overwritten. Edit the `_async/`
> originals instead, then run `just generate-sync`.

Code and docstrings that must differ between the two clients use the generator's directives, described in
[AGENTS.md](AGENTS.md#async-first-generate-sync).

### Endpoint map

`docs/endpoints.md` maps each Discogs endpoint to the SDK call that reaches it, one row per verb and route. It is
generated from the SDK sources (`src/discogs_sdk/_async/` and `src/discogs_sdk/oauth.py`), never by hand nor from the
API reference, so the `endpoints-check` hook (run by the git hooks, `just qa` and the CI quality job, which also gates
every release) can fail a stale copy. The packaged agent skill carries a copy of the page in its `references/`, which
`just generate-endpoints` regenerates too. After adding or renaming a resource method, run `just generate-endpoints`
and commit the result. The generator stops with an error on a resource class it cannot reach from `client`, so a new
resource is never left out silently.

### Endpoint coverage

`just endpoints-coverage` runs two checks against the local API reference in `reference/discogs_api/`:

- **Routes.** It fails on a documented route the SDK never reaches and on a route the SDK calls that the reference does
  not document. It checks routes only — not query or body parameters, which the reference describes in prose.
- **Payloads.** Every JSON example in the reference must be claimed by an `Example` in `tests/documented_payloads.py`
  (a payload, envelope or error), and no two payloads may claim the same example at the same path. A claimed payload
  must have the example's keys, give or take the `extra_keys` it declares; dynamic payloads, envelopes and errors are
  checked structurally. The rules are in the docstring of `scripts/check_endpoint_coverage.py`. After refreshing the
  reference (`just update-api-docs --write`), a new example shows up as `UNCLAIMED`: register it there.

It is not part of `just qa`, because that reference copy is git-ignored and so is absent in CI.

Adding `--compare-upstream` runs drift probes against a fresh clone of `python3-discogs-client`: markers that must
stay present, or substrings that must stay absent, in its sources. They are signals, not proof — a firing probe
means re-read its sources before trusting the comparison table. Run it before editing that table.

### Adding a new resource

1. Add the resource to `src/discogs_sdk/_async/resources/`
2. Wire it into `src/discogs_sdk/_async/_client.py`. Resource classes are reached through the client and are not
   exported
3. Add its models to `src/discogs_sdk/models/` and export them from `models/__init__.py` and `__init__.py`
4. Run `just generate-sync` to create the sync source code
5. Write tests in `tests/async/` and their twins in `tests/sync/`
6. Run `just generate-endpoints` to update the endpoint map and its skill copy

## Testing

### Unit tests

```bash
just test                                                              # All unit tests
just test tests/async/test_releases.py                                 # Single file
just test tests/async/test_releases.py -k test_get_resolves_to_release # Single test
```

Unit tests use [respx](https://github.com/lundberg/respx) to mock HTTP at the transport level. They never hit the
network.

### Integration tests

Integration tests run against the real Discogs API. They are excluded from `just test` and only run explicitly:

```bash
just test-integration      # Authenticated tests: personal token, and OAuth when its tokens are set
just test-unauthenticated  # Tests that send no credentials at all
```

`just test-integration` needs `DISCOGS_TOKEN`; `just test-unauthenticated` needs nothing.

**Use a disposable test account.** Some of these tests mutate account data: they add and remove collection
instances, wantlist entries and folders. They only touch what they create and skip a wantlist entry that already
exists, but a crash between creation and cleanup can still leave a stray entry behind. Never point them at an
account whose collection, wantlist or inventory you care about.

#### Personal token setup

1. Create a Discogs account (or use an existing one) at https://www.discogs.com
2. Generate a personal access token at https://www.discogs.com/settings/developers
3. Add it to your `.env` file:

```
DISCOGS_TOKEN=your_token_here
```

With direnv, run `direnv allow` (or `direnv reload`) to pick up the change.

#### OAuth token setup

Some integration tests verify that OAuth 1.0a signed requests work against the real API. These require pre-authorized
tokens.

**One-time setup:**

1. Register an application at https://www.discogs.com/settings/developers to get a consumer key and secret.

2. Add them to `.env`:

```
DISCOGS_CONSUMER_KEY=your_consumer_key
DISCOGS_CONSUMER_SECRET=your_consumer_secret
```

3. Reload the environment so the new variables are available:

```bash
# If you use direnv:
direnv allow

# Otherwise, source .env manually:
export $(grep -v '^#' .env | xargs)
```

4. Run the interactive verification script:

```bash
just verify-oauth
```

This will:
  - Request an OAuth request token from the Discogs API
  - Open your browser to the Discogs authorization page
  - Prompt you to paste the verification code after you approve
  - Exchange it for access tokens
  - Verify the tokens work by making an authenticated API call
  - Print the tokens to add to `.env`

5. Add the printed tokens to `.env`:

```
DISCOGS_CONSUMER_KEY=your_consumer_key
DISCOGS_CONSUMER_SECRET=your_consumer_secret
DISCOGS_ACCESS_TOKEN=your_access_token
DISCOGS_ACCESS_TOKEN_SECRET=your_access_token_secret
```

OAuth tokens do not expire unless revoked. This setup only needs to be done once.

From then on, `just test-integration` automatically runs both the personal token and OAuth integration tests.

#### Rate limits

The Discogs API allows 60 authenticated requests per minute, and 25 per minute per IP address without credentials.

- The authenticated suite has 32 tests sharing one session-scoped client, and `tests/integration/conftest.py` budgets
  it at under 40 calls. Every read-back of a write polls through `eventually()`, though, which retries its check (up
  to six attempts, each of which can send several requests, as `tests/integration/test_wantlist.py` explains) while
  the write is not yet visible, so a slow run spends more. Avoid running the suite in a tight loop.
- **Keep the two recipes apart.** The anonymous limit is per IP and the authenticated calls use it up, so running
  `just test-unauthenticated` within a minute of `just test-integration` makes the anonymous tests fail with 429.

## Code style

- Python 3.10+ (CI tests through 3.15), ruff targets py310 to match `requires-python`, line length 88
- Formatting and linting handled by ruff (`just format`, `just lint-fix`)
- Type checking with ty (`just type-check`)
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `<type>: <description>`
  (e.g., `feat: add list items resource`, `fix: handle rate limit retry`)

## Submitting a pull request

1. Fork the repo and create a branch from `main` named `<type>/issue-<N>-<slug>` for an issue, otherwise
   `<type>/<slug>`, where `<type>` is the Conventional Commits type of the change (e.g., `fix/issue-42-rate-limit-retry`,
   `feat/add-list-items`)
2. Make your changes — if touching `_async/`, run `just generate-sync`
3. Add or update tests
4. Run `just qa` to catch issues before CI does
5. Push and open a PR against `main`, referencing any related issues (e.g., "Fixes #42")

### PR checklist

Before opening a PR, make sure the following are done:

- [ ] Tests added or updated and passing (`just test`)
- [ ] `just qa` passes
- [ ] Sync code regenerated if `_async/` changed (`just generate-sync`)
- [ ] Endpoint map and its skill copy regenerated if a resource method changed (`just generate-endpoints`)
- [ ] New public APIs exported from `__init__.py`
- [ ] The change follows the [design principles](README.md#design-principles)

### What to expect

A maintainer will review your PR, usually within a few days. Change requests are normal and collaborative.
Push additional commits to the same branch; no need to squash. Every commit on the branch must be signed and show as
verified on GitHub: `main` requires signed commits, and an unsigned one blocks the merge until it is re-signed and
force-pushed. Pull requests are squash-merged, so the pull request title becomes the commit subject on `main`, and
git-cliff builds the changelog from it: write it as a Conventional Commit.

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE.txt).
