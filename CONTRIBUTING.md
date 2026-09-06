# Contributing

Thank you for your interest in contributing to **mattermind**!

## Development Setup

```bash
git clone https://github.com/bedrock-python/mattermind
cd mattermind
uv sync
pre-commit install
```

## Workflow

1. Create a branch: `feat/ISSUE-123__short_description`
2. Make changes, write tests
3. Run checks: `make check && make test`
4. Commit using [Conventional Commits](https://www.conventionalcommits.org/): `feat(agent): add mm_search pagination`
5. Open a pull request

## Commit Convention

```
<type>(scope): <message>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`

## Code Style

- `ruff` for formatting and linting (`make fmt`)
- `mypy` in strict mode (`make check`)
- No `Any`, no `datetime.utcnow()`, no TODO/FIXME
- Type hints on every function and class member

## The agents page

`docs/agents.md` is the whole tool on one page, written for a coding assistant: every
command and flag, every configuration key and its default, the tools the model is given,
the rules that break a run when they are broken, the mistakes assistants make, and a map of
which page to fetch for the rest. People hand it to an assistant instead of the site, which
is what makes a stale one worse than none — it teaches a model a flag or a default that no
longer exists.

It is part of the public surface, so it changes in the same pull request that surface does:
a command or flag added, renamed or removed, a changed default, a new environment variable,
a new rule a user has to obey. A new docs page means a new row in the documentation map.
The review check is mechanical — if the diff changes the CLI, the config models or the
Python surface and `docs/agents.md` is untouched, the pull request is not finished.

The page carries its own weight only if it stays fetchable as text. Every page of the site
is written a second time as raw Markdown next to its HTML by `scripts/emit_markdown.py`,
which the Docs workflow runs after the build; the **Copy page** control above each page
reads those files. A page whose Markdown would not read as the page — the generated API
reference — declines both with `copy_page: false` in its front matter.

## Running Tests

```bash
make test          # unit tests only (no external deps)
make test-all      # includes integration tests (requires real MM + LLM)
```

## Reporting Bugs

Open an issue with:
- `mattermind version` output
- Minimal reproduction steps
- What you expected vs what happened
