# Commands

## `mattermind ask <question>`

Ask a natural-language question about your Mattermost workspace.

```bash
mattermind ask "what was discussed about the auth migration?"

# with per-call overrides
mattermind ask "latest incidents?" \
  --mm-url https://mm.company.com \
  --mm-token $MM_TOKEN \
  --team engineering \
  --model gpt-4o
```

## `mattermind init`

Interactive wizard that creates `~/.config/mattermind/config.yaml`.

```bash
mattermind init
```

## `mattermind config show`

Print the resolved config with secrets masked.

```bash
mattermind config show
mattermind --config ./custom.yaml config show
```

## `mattermind config validate`

Validate the config, then test connectivity to both Mattermost and the LLM endpoint —
`GET /api/v4/users/me` on the Mattermost server, `GET /models` on the LLM base URL. Exits
`1` if the config is invalid or either endpoint refuses.

```bash
mattermind config validate
```

## `mattermind version`

Print the installed version.

## Global Flags

These work with every command, before or after the subcommand — `mattermind --json ask
"..."` and `mattermind ask "..." --json` are the same command:

| Flag | Description |
|---|---|
| `--config PATH` / `-c` | Path to YAML config file |
| `--verbose / -v` | Show tool calls as JSON, full tracebacks |
| `--quiet / -q` | Plain answer only, no UI chrome |
| `--json` | Machine-readable JSON output |
| `--no-color` | Disable ANSI colours |
