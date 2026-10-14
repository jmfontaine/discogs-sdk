# AI coding agents

Coding agents tend to write python3-discogs-client code (`import discogs_client`) when asked for discogs-sdk, or to
confuse it with the unrelated `crate-ai/discogs-sdk`, and they miss its lazy-loading, pagination and write semantics.
discogs-sdk ships an agent skill inside the package that covers these points, matched to the version you install.

## Install the skill

The skill lives in the installed package, at `site-packages/discogs_sdk/.agents/skills/discogs-sdk/` (the
[library-skills](https://library-skills.io/create/) convention), with copies of the pagination, errors, caching,
endpoint-map and migration pages for that version beside it. The `library-skills` command links it into your project
where agents look for skills.

Declare discogs-sdk as a dependency of the project and install it, for example with `uv add discogs-sdk`. By default
`library-skills` only offers skills from your direct dependencies, so the interactive run and `--yes` on its own do
not discover a copy that arrived as someone else's dependency or that you installed without declaring it. Naming the
skill with `--skill discogs-sdk` (or passing `--all`) looks at every installed package.

Run it interactively from the project directory and pick the skill and the targets:

```bash
uvx library-skills
```

Or non-interactively, for both `.agents/skills/` and Claude Code's `.claude/skills/`:

```bash
uvx library-skills --claude --yes --skill discogs-sdk
```

Omit `--claude` when you do not use Claude Code; most other agents (Codex, Cursor, GitHub Copilot, OpenCode and
others) read `.agents/skills/`. Name the skill with `--skill discogs-sdk`: `--yes` on its own reports the skill as
new but installs nothing.

`library-skills` creates relative symlinks into the virtual environment, so upgrading discogs-sdk updates the skill
too, and the links can be committed when the project uses a repo-local `.venv`.
`uvx library-skills --claude --check` exits 1 when those links have drifted from the installed packages.

On a system without practical symlink support, such as Windows without Developer Mode, add `--copy` to copy the
files instead. A copy does not follow upgrades, and `library-skills` will not overwrite it later (it reports the
directory as hand-authored), so after each upgrade delete `.agents/skills/discogs-sdk` (and
`.claude/skills/discogs-sdk`) and run the command again. `--check` cannot tell a current copy from a stale one.

## Agents that do not read skills

For an agent that reads only a rules file, paste this into `AGENTS.md`, a file under `.cursor/rules/`, or
`.github/copilot-instructions.md`:

```markdown
## discogs-sdk
- This project uses discogs-sdk (PyPI `discogs-sdk`, `import discogs_sdk`), not python3-discogs-client (`import discogs_client`) or crate-ai/discogs-sdk. Never use their APIs.
- One client per program: `with Discogs() as client:` or `async with AsyncDiscogs() as client:`; the token comes from `DISCOGS_TOKEN`.
- `.get()` returns a lazy proxy and sends nothing; the first data attribute access fetches, so catch `NotFoundError` there.
- Async: `await` a proxy for its model. The model has no sub-resources, so keep the proxy for chaining (`artist_proxy.releases.list()`); use `async for` on pages.
- `search()` and paginated `.list()` methods make one logical GET per page: a cache hit sends no request (one if the cached entry no longer parses), retries can send several, and each network attempt consumes the budget (60/min, 25/min anonymous). `break` early; never `list()` a large result set.
- After a write fails ambiguously, poll inside `client.no_cache()` with a new proxy or iterator; never resubmit a create blindly.
- A custom `http_client` must be an `httpx2` client, never `httpx`; the SDK does not close it.
- Endpoint-to-method map: https://github.com/jmfontaine/discogs-sdk/blob/main/docs/endpoints.md
```

The skill itself carries more: the full rules, runnable examples, and the reference pages for the installed version.
See also [Behaviors to know](getting-started.md#behaviors-to-know) and the
[migration guide](migrating-from-python3-discogs-client.md).
