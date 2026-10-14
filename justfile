set quiet := true

_list:
    just --list

# Preview release notes for unreleased changes
changelog-preview:
    uvx git-cliff --unreleased

# Check for unused or undeclared deps
deps-unused:
    uv run deptry src

# Update deps to latest versions
deps-update:
    uv lock --upgrade
    uv sync --all-groups

# Find dead code
dead-code:
    scripts/check_dead_code.sh

# Check docs/endpoints.md is up to date with the SDK sources
endpoints-check:
    uv run python scripts/generate_endpoints.py --check

# Verify the SDK reaches every documented endpoint (add --compare-upstream for the README comparison)
endpoints-coverage *args:
    uv run python scripts/check_endpoint_coverage.py {{ args }}

# Run formatters
format:
    uv run pyproject-fmt pyproject.toml
    uv run ruff format

# Check formatting without modifying files
format-check:
    uv run pyproject-fmt --check pyproject.toml
    uv run ruff format --check

# Generate docs/endpoints.md (the endpoint-to-SDK-call map) from the SDK sources, then the skill's copy of it
generate-endpoints: && generate-skill-refs
    uv run python scripts/generate_endpoints.py

# Copy the docs pages the packaged agent skill uses into its references/
generate-skill-refs:
    uv run python scripts/generate_skill_refs.py

# Generate sync code from async sources
generate-sync:
    uv run python scripts/generate_sync.py

# Run linter
lint:
    uv run ruff check

# Run linter and fix issues
lint-fix:
    uv run ruff check --fix

# Run pre-commit on all files
pre-commit:
    uv run pre-commit run --all-files

# Install pre-commit hooks
pre-commit-install:
    uv run pre-commit install

# Update pre-commit hooks to latest versions
pre-commit-update:
    uv run pre-commit autoupdate --freeze

# Run all quality assurance checks: every pre-commit hook on all files, then the type-completeness audit
qa: pre-commit verify-types

# Tag the merged origin/main, push the tag, and monitor the publish workflow
release:
    #!/usr/bin/env bash
    set -euo pipefail
    # Only the merged version bump may be tagged: a squash merge creates a new commit,
    # so a tag on the release branch would name a commit that never reaches main.
    echo "Fetching origin/main..."
    git fetch --quiet origin main
    if [ "$(git rev-parse HEAD)" != "$(git rev-parse refs/remotes/origin/main)" ]; then
        echo "Error: HEAD is not origin/main. Merge the release pull request, then run" \
            "'git checkout main && git pull --ff-only' and rerun 'just release'."
        exit 1
    fi
    version=$(uv run python -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])")
    tag="v${version}"
    if git rev-parse "$tag" >/dev/null 2>&1; then
        echo "Error: tag $tag already exists"
        exit 1
    fi
    if [ -n "$(git status --porcelain)" ]; then
        echo "Error: working tree is not clean"
        exit 1
    fi
    echo "Creating signed tag $tag..."
    git tag -s "$tag" -m "Release $tag"
    echo "Pushing $tag to origin..."
    git push origin "$tag"
    # The push above is irreversible: from here on, never push again, and tell the
    # user not to rerun this recipe if something fails.
    poll_interval=5
    poll_attempts=24
    echo "Waiting for the publish workflow run to register..."
    run_id=""
    for ((attempt = 1; attempt <= poll_attempts; attempt++)); do
        sleep "$poll_interval"
        # `// empty` turns "no run yet" into an empty string instead of `null`, and a
        # transient gh failure counts as "no run yet" rather than aborting the loop.
        run_id=$(gh run list --workflow=publish.yml --branch="$tag" --limit=1 --json=databaseId --jq='.[0].databaseId // empty') || run_id=""
        if [ -n "$run_id" ]; then
            break
        fi
    done
    if [ -z "$run_id" ]; then
        echo "Error: no publish workflow run registered for $tag within $((poll_interval * poll_attempts))s." >&2
        echo "The tag $tag is already pushed. Do not rerun 'just release'." >&2
        echo "Find the run with 'gh run list --workflow=publish.yml' or on the repository's Actions page ('gh workflow view publish.yml --web')." >&2
        exit 1
    fi
    echo "Watching publish run $run_id..."
    gh run watch --exit-status "$run_id"

# Set local dev environment up
setup:
    uv sync --all-groups  # Install dependencies
    uv run pre-commit install  # Install pre-commit hooks

# Check the agent skill's references/ match the docs pages they copy
skill-refs-check:
    uv run python scripts/generate_skill_refs.py --check

# Check sync code is up to date with async sources
sync-check:
    uv run python scripts/generate_sync.py --check

# `--cov` takes an optional source, so `--cov-config` follows it to keep a first argument such as a test path from
# being read as one; [tool.coverage] in pyproject.toml sets the source and the missing-lines column.

# Run tests
test *args:
    uv run pytest --cov --cov-config=pyproject.toml {{ args }}

# Run authenticated integration tests
test-integration *args:
    uv run pytest -m 'integration and not unauthenticated' {{ args }}

# Run integration tests that use no credentials (keep them off the same minute as the authenticated ones)
test-unauthenticated *args:
    uv run pytest -m 'integration and unauthenticated' {{ args }}

# Compare reference/discogs_api/ with the official API reference (--diff, --check, --write)
update-api-docs *args:
    uv run python scripts/update_api_docs.py {{ args }}

# Run type checker
type-check:
    uv run ty check

# Verify OAuth flow interactively
verify-oauth:
    uv run python scripts/verify_oauth.py

# Audit public API type annotation coverage
verify-types:
    uv run pyright --ignoreexternal --verifytypes discogs_sdk
