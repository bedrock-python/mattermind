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
