# Output Modes

## Default (Rich Markdown)

Full interactive experience:

1. ASCII banner
2. Query panel
3. Live status lines as the agent works
4. Rendered markdown answer with clickable OSC8 links
5. Thread tree showing what was explored
6. Summary panel (threads, tool calls, tokens, time)

Requires a terminal that supports ANSI escape codes.

## `--quiet`

Plain text answer only — no banner, no progress, no tree, no summary. Useful for reading
in a pager:

```bash
mattermind ask "..." --quiet | less
```

## `--json`

Single JSON object on stdout, schema:

```json
{
  "answer": "...",
  "threads_explored": 7,
  "tool_calls_made": 12,
  "token_usage": {
    "prompt_tokens": 14200,
    "completion_tokens": 4220,
    "total_tokens": 18420
  },
  "elapsed_seconds": 14.2,
  "incomplete": false,
  "permalinks": ["https://mm.company.com/team/pl/abc123", "..."],
  "explored_threads": [
    {
      "post_id": "abc123",
      "channel": "engineering",
      "title": "auth service migration",
      "permalink": "https://mm.company.com/team/pl/abc123"
    }
  ]
}
```

`output.format: json` in the config file prints the same body without the flag.

Ideal for scripts and automation:

```bash
mattermind ask "who owns billing?" --json | jq -r .answer
```

## `--no-color`

Strips all ANSI codes. Useful when piping to a file or a tool that doesn't handle colour.
