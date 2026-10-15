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
release: _require-synced-main
    #!/usr/bin/env bash
    set -euo pipefail
    # _require-synced-main has checked that HEAD is origin/main: only the merged version
    # bump may be tagged, since a squash merge creates a new commit and a tag on the
    # release branch would name a commit that never reaches main.
    version=$(uv version --short)
    # publish.yml uploads whatever version the tag names, so a development or
    # pre-release version must never be tagged.
    if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "Error: version $version is not a release version (X.Y.Z). Run 'just release-prepare' first." >&2
        exit 1
    fi
    tag="v${version}"
    if git rev-parse "$tag" >/dev/null 2>&1; then
        echo "Error: tag $tag already exists"
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
    echo "Released $tag. Run 'just release-next' (or 'just release-next patch|major') to start the next development version."

# Open the pull request that starts the next development version: bump is minor, patch or major
release-next bump="minor": _require-synced-main
    #!/usr/bin/env bash
    set -euo pipefail
    case {{ quote(bump) }} in
        minor | patch | major) ;;
        *)
            echo "Error: bump must be minor, patch or major, not {{ quote(bump) }}" >&2
            exit 1
            ;;
    esac
    current=$(uv version --short)
    if [[ ! "$current" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "Error: version $current is not a release version (X.Y.Z), so development is already open." >&2
        exit 1
    fi
    if ! git ls-remote --exit-code --tags origin "refs/tags/v$current" >/dev/null; then
        echo "Error: tag v$current is not on origin. Release it with 'just release' first." >&2
        exit 1
    fi
    next=$(uv version --bump {{ quote(bump) }} --dry-run --short)
    # Set .dev0 explicitly: `uv version --bump minor --bump dev` gives .dev1.
    {{ just_executable() }} _version-pr "release/v$next.dev0" "$next.dev0" \
        "chore: start $next development" \
        "Set the version to $next.dev0 in pyproject.toml and uv.lock, so builds from main sort below the $next release, and regenerate the packaged agent skill's references, whose links name main for a development version."

# Open the release pull request: version defaults to the development version without its .devN
release-prepare version="": _require-synced-main
    #!/usr/bin/env bash
    set -euo pipefail
    current=$(uv version --short)
    if [[ ! "$current" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.dev[0-9]+$ ]]; then
        echo "Error: version $current is not a development version (X.Y.Z.devN). Run 'just release-next' first." >&2
        exit 1
    fi
    version={{ quote(version) }}
    if [ -z "$version" ]; then
        version=$(uv version --bump stable --dry-run --short)
    elif [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "Error: $version is not a release version (X.Y.Z)." >&2
        exit 1
    fi
    # --exit-code returns 2 when the tag is absent; anything else (origin unreachable) must stop here too.
    status=0
    git ls-remote --exit-code --tags origin "refs/tags/v$version" >/dev/null || status=$?
    if [ "$status" -ne 2 ]; then
        [ "$status" -eq 0 ] && echo "Error: tag v$version already exists on origin." >&2
        exit 1
    fi
    {{ just_executable() }} _version-pr "release/v$version" "$version" \
        "chore: release v$version" \
        "Set the version to $version for release in pyproject.toml and uv.lock, and regenerate the packaged agent skill's references, whose links now name the v$version tag. Merging this pull request approves the release; 'just release' then tags it."

# Refuse to go on unless HEAD is the freshly fetched origin/main and the working tree is clean
_require-synced-main:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Fetching origin/main..."
    git fetch --quiet origin main
    if [ "$(git rev-parse HEAD)" != "$(git rev-parse refs/remotes/origin/main)" ]; then
        echo "Error: HEAD is not origin/main. Merge any pending version pull request, run" \
            "'git checkout main && git pull --ff-only', then rerun." >&2
        exit 1
    fi
    if [ -n "$(git status --porcelain)" ]; then
        echo "Error: working tree is not clean" >&2
        exit 1
    fi

# Commit a version change on a new branch, with the skill references regenerated, and open its pull request
[positional-arguments]
_version-pr branch version subject body:
    #!/usr/bin/env bash
    set -euo pipefail
    branch=$1 version=$2 subject=$3 body=$4
    git switch --create "$branch"
    # Until the commit lands, a failure leaves the branch checked out with uncommitted changes.
    trap 'echo "Error: stopped on $branch. Recover with: git reset --hard && git switch main && git branch -D $branch" >&2' ERR
    uv version "$version"
    uv run python scripts/generate_skill_refs.py
    git add pyproject.toml uv.lock src/discogs_sdk/.agents/skills/discogs-sdk/references
    git commit --quiet -S -m "$subject" -m "$body"
    trap - ERR
    git push --quiet --set-upstream origin "$branch"
    gh pr create --base main --head "$branch" --title "$subject" --body "$body"

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
