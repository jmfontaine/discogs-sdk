# Contributing to discogs-sdk

Contributions are welcome — bug fixes, new features, documentation, test coverage.
This guide walks you through the development setup and PR process.

For larger changes, please open an issue first so we can discuss the approach
before you invest significant time.

## Reporting bugs and requesting features

Before opening an issue, search [existing issues](https://github.com/jmfontaine/discogs-sdk/issues) to avoid duplicates.

**Bug reports** should include:
- Python version and discogs-sdk version (`python --version`, `pip show discogs-sdk`)
- Minimal code example that reproduces the issue
- Full traceback or error message

**Feature requests** — describe the problem you want to solve, not just the solution.
For new API resource coverage, note which Discogs API endpoints are involved.

## Setup

```bash
git clone https://github.com/jmfontaine/discogs-sdk.git
cd discogs-sdk
just setup
```

This installs dependencies with [uv](https://docs.astral.sh/uv/) and sets up pre-commit hooks.

## Development workflow

The task runner is `just` (not `make`). Key commands:

```bash
just test               # Unit tests with coverage (fast, no network)
just qa                 # All checks: dead-code, format, lint, type-check, unused-deps
just lint-fix           # Auto-fix lint issues
just format             # Auto-format code
just generate-sync      # Regenerate _sync/ from _async/ sources
```

### Async-first architecture

`src/discogs_sdk/_async/` is the source of truth. The `_sync/` directory is auto-generated via AST transformation.

> [!WARNING]
> `_sync/` source files and `tests/sync/` tests are auto-generated. Never edit them
> directly — your changes will be overwritten. Edit the `_async/` originals instead,
> then run `just generate-sync`.

### Adding a new resource

1. Add the resource to `src/discogs_sdk/_async/resources/`
2. Wire it into `src/discogs_sdk/_async/_client.py`
3. Add models to `src/discogs_sdk/models/`, export from `models/__init__.py` and `__init__.py`
4. Write tests in `tests/async/`
5. Run `just generate-sync` to create the sync variant and tests

## Testing

### Unit tests

```bash
just test                                          # All unit tests
just test tests/async/test_releases.py             # Single file
just test tests/async/test_releases.py -k test_get # Single test
```

Unit tests use [respx](https://github.com/lundberg/respx) to mock HTTP at the transport level. They never hit the network.

### Integration tests

Integration tests run against the real Discogs API. They are excluded from `just test` and only run explicitly:

```bash
just test-integration
```

#### Personal token setup

1. Create a Discogs account (or use an existing one) at https://www.discogs.com
2. Generate a personal access token at https://www.discogs.com/settings/developers
3. Add it to your `.env` file:

```
DISCOGS_TOKEN=your_token_here
```

If you use [direnv](https://direnv.net/), the `.envrc` already loads `.env` automatically.

#### OAuth token setup

Some integration tests verify that OAuth 1.0a signed requests work against the real API. These require pre-authorized tokens.

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

The Discogs API allows 60 authenticated requests per minute. The integration test suite uses ~30 calls with a session-scoped client, so it stays well within the limit. Avoid running the suite in a tight loop.

## Code style

- Python 3.10+, ruff targets 3.14, line length 120
- Formatting and linting handled by ruff (`just format`, `just lint`)
- Type checking with ty (`just type-check`)

## Submitting a pull request

1. Fork the repo and create a branch from `main` (e.g., `fix-rate-limit-retry`, `add-list-items`)
2. Make your changes — if touching `_async/`, run `just generate-sync`
3. Add or update tests
4. Run `just qa` to catch issues before CI does
5. Push and open a PR against `main`, referencing any related issues (e.g., "Fixes #42")

### PR checklist

- [ ] Tests added or updated and passing (`just test`)
- [ ] `just qa` passes (format, lint, type-check, dead-code, unused-deps)
- [ ] Sync code regenerated if `_async/` changed (`just generate-sync`)
- [ ] New public APIs exported from `__init__.py`

### What to expect

A maintainer will review your PR, usually within a few days. Change requests are
normal and collaborative. Push additional commits to the same branch — no need
to force-push or squash until asked.

## License

By contributing, you agree that your contributions will be licensed under the
[Apache License 2.0](LICENSE.txt).
