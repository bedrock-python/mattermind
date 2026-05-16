# Quickstart

## 1. Install

```bash
# Recommended: uv tool (isolated, globally available)
uv tool install mattermind

# Or: pip
pip install mattermind
```

## 2. Configure

Run the interactive wizard:

```bash
mattermind init
```

It will ask for your Mattermost URL, Personal Access Token, team name, LLM endpoint, and model, then write `~/.config/mattermind/config.yaml`.

**Or** set environment variables directly:

```bash
export MATTERMIND_MM_URL=https://mm.company.com
export MATTERMIND_MM_TOKEN=your-pat-here
export MATTERMIND_TEAM=engineering
export MATTERMIND_LLM_BASE_URL=https://api.openai.com/v1
export MATTERMIND_LLM_API_KEY=sk-...
export MATTERMIND_MODEL=gpt-4o-mini
```

## 3. Ask a question

```bash
mattermind ask "what was decided about the DB migration?"
```

## 4. Validate your setup

```bash
mattermind config validate
```

This tests connectivity to both Mattermost and the LLM endpoint.

## Modes

```bash
# Quiet (plain answer, no UI chrome)
mattermind ask "..." --quiet

# JSON (machine-readable, for piping)
mattermind ask "..." --json | jq .answer

# Verbose (shows tool calls as JSON)
mattermind ask "..." --verbose
```
