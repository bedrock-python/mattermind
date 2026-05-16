# mattermind

**Ask natural-language questions about your Mattermost workspace.**

mattermind is a CLI tool that uses an LLM agent with tool-calling to search your Mattermost team, follow permalink chains between threads, and return a structured, cited answer.

```bash
$ mattermind ask "что решили про переезд сервисов из ORG_A в ORG_B?"
```

The agent:

1. Expands your query into 2–5 search variants (synonyms, RU/EN, team jargon)
2. Searches Mattermost, picks the most relevant threads
3. Fetches full threads, finds embedded permalinks
4. Follows links recursively (configurable depth)
5. Returns a structured markdown answer with clickable citations

## Quick Start

```bash
uv tool install mattermind   # or: pip install mattermind

mattermind init              # interactive setup wizard
mattermind ask "your question"
```

See the [Quickstart guide](guide/quickstart.md) for details.

## Key Features

- **Agentic loop** — LLM decides what to search, what to fetch, when to stop
- **Permalink following** — automatically resolves cross-thread links
- **Rich terminal UI** — live status, thread tree, OSC8 clickable links
- **Flexible config** — YAML file, env vars, CLI flags (merges all three)
- **JSON mode** — `--json` for scripting and automation
- **Any OpenAI-compatible LLM** — set `base_url` to use local models, Groq, etc.
