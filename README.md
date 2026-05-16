# mattermind

[![CI](https://github.com/bedrock-python/mattermind/actions/workflows/ci.yml/badge.svg)](https://github.com/bedrock-python/mattermind/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mattermind)](https://pypi.org/project/mattermind/)
[![Python](https://img.shields.io/pypi/pyversions/mattermind)](https://pypi.org/project/mattermind/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-bedrock--python.github.io%2Fmattermind-blue)](https://bedrock-python.github.io/mattermind/)

Ask natural-language questions about your Mattermost workspace using LLM tool-calling.

**[Documentation](https://bedrock-python.github.io/mattermind/)**

## Features

- Full-text search across your Mattermost team via the REST API v4
- Agentic loop with tool calling (search, get thread, resolve permalink, look up users)
- Follows permalink chains up to a configurable depth
- Cites every claim with clickable permalink links
- Rich terminal UI with progress, answer rendering, and token usage summary
- Interactive TUI chat interface (`mattermind chat`)
- JSON output mode for scripting (`--json`)
- Token budget protection with interactive continue prompt
- SSO-compatible: authenticate via session token (MMAUTHTOKEN) or login/password
- Self-signed certificate support (`verify_ssl: false`)
- Interactive setup wizard (`mattermind init`)

## Installation

```bash
uv tool install mattermind
# or from source:
uv sync --extra dev
```

## Quick Start

```bash
# Interactive setup
mattermind init

# Or: save your Mattermost session token
mattermind login

# List available teams and save your choice
mattermind teams

# Ask a question
mattermind ask "What was decided about the auth service migration?"

# Interactive TUI chat
mattermind chat

# JSON output
mattermind ask "latest incidents?" --json | jq .answer
```

## Authentication

Mattermind supports two authentication methods:

**Token (recommended for SSO environments):**
```bash
mattermind login
# Follow the instructions to copy MMAUTHTOKEN from browser DevTools
```

Or set in config:
```yaml
mattermost:
  token: ${MM_TOKEN}
```

**Login / Password:**
```yaml
mattermost:
  login: user@company.com
  password: ${MM_PASSWORD}
```

## Configuration

Priority (lowest to highest): defaults → `~/.config/mattermind/config.yaml` → env vars → CLI flags.

```yaml
# ~/.config/mattermind/config.yaml
mattermost:
  url: https://mm.company.com
  token: ${MM_TOKEN}          # env interpolation supported
  team: engineering
  verify_ssl: true             # set false for self-signed certs

llm:
  base_url: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
  model: gpt-4o-mini
  verify_ssl: true

agent:
  max_iterations: 15
  total_token_budget: 200000
  max_threads_per_query: 20

output:
  format: markdown             # markdown | plain
  show_token_usage: true
  show_timings: true
```

### Environment Variables

| Variable | Description |
|---|---|
| `MATTERMIND_MM_URL` | Mattermost server URL |
| `MATTERMIND_MM_TOKEN` | Personal Access Token / MMAUTHTOKEN |
| `MATTERMIND_MM_LOGIN` | Login (email or username) |
| `MATTERMIND_MM_PASSWORD` | Password |
| `MATTERMIND_TEAM` | Team slug |
| `MATTERMIND_MM_VERIFY_SSL` | Verify Mattermost TLS (`true`/`false`) |
| `MATTERMIND_LLM_BASE_URL` | LLM API base URL (OpenAI-compatible) |
| `MATTERMIND_LLM_API_KEY` | LLM API key |
| `MATTERMIND_MODEL` | Model name |
| `MATTERMIND_LLM_VERIFY_SSL` | Verify LLM gateway TLS (`true`/`false`) |

## Commands

```
mattermind ask <question>   Ask a question about your Mattermost workspace
mattermind chat             Launch interactive TUI chat interface
mattermind teams            List available teams and save your selection
mattermind login            Save a session token (MMAUTHTOKEN) to config
mattermind init             Interactive config setup wizard
mattermind config show      Print resolved config (secrets masked)
mattermind config validate  Validate config file
mattermind version          Print version
```

### Global flags

```
-c / --config PATH    Path to config YAML file
-v / --verbose        Enable verbose output (shows tool calls)
-q / --quiet          Suppress banner and status lines
--json                Output result as JSON (machine-readable)
--no-color            Disable colour output
```

## Development

```bash
make install    # install deps
make fmt        # format + fix lint
make check      # lint + type-check
make test       # run unit tests with coverage
```

## Architecture

```
src/mattermind/
├── cli/        — Typer CLI app, commands, app context
├── config/     — Pydantic models, YAML loader, env interpolation, wizard
├── mattermost/ — Async httpx client, Mattermost REST API v4, domain models
├── agent/      — Agentic loop, tool definitions, system prompt, state
└── ui/         — Rich rendering, Textual TUI, error panels
```
