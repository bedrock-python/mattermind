# Configuration

Configuration is merged from three sources, in order of increasing priority:

```
built-in defaults < config.yaml < environment variables < CLI flags
```

## Config File

Default location: `~/.config/mattermind/config.yaml`

Override with `--config PATH`.

```yaml
mattermost:
  url: https://mm.company.com
  token: ${MM_TOKEN}           # env interpolation: ${VAR} or ${VAR:-default}
  team: engineering
  timeout_seconds: 30
  rate_limit_rps: 10
  verify_ssl: true             # false for a self-signed certificate

llm:
  base_url: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
  model: gpt-4o-mini
  temperature: 0.2
  max_tokens_per_response: 4000
  request_timeout_seconds: 120
  verify_ssl: true

agent:
  max_iterations: 15           # how many times LLM may call tools
  max_threads_per_query: 20
  max_link_depth: 2            # how deep to follow permalinks
  total_token_budget: 200000
  parallel_tool_calls: true

output:
  show_thread_tree: true
  show_token_usage: true
  show_timings: true
  format: markdown             # markdown | plain | json (json prints the --json body)

logging:
  level: INFO                  # DEBUG | INFO | WARNING | ERROR | CRITICAL
```

Unknown keys are rejected: a misspelled key fails validation with the key named in the
error, rather than being ignored.

## Environment Variables

| Variable | Config key |
|---|---|
| `MATTERMIND_MM_URL` | `mattermost.url` |
| `MATTERMIND_MM_TOKEN` | `mattermost.token` |
| `MATTERMIND_MM_LOGIN` | `mattermost.login` |
| `MATTERMIND_MM_PASSWORD` | `mattermost.password` |
| `MATTERMIND_TEAM` | `mattermost.team` |
| `MATTERMIND_MM_VERIFY_SSL` | `mattermost.verify_ssl` |
| `MATTERMIND_LLM_BASE_URL` | `llm.base_url` |
| `MATTERMIND_LLM_API_KEY` | `llm.api_key` |
| `MATTERMIND_MODEL` | `llm.model` |
| `MATTERMIND_LLM_VERIFY_SSL` | `llm.verify_ssl` |

There is no environment variable for any `agent`, `output` or `logging` field; those come
from the file.

## CLI Flags (`ask` command)

```
--mm-url TEXT
--mm-token TEXT
--mm-login TEXT
--mm-password TEXT
--team TEXT
--llm-base-url TEXT
--llm-api-key TEXT
--model TEXT
```

## Env Interpolation

String values in YAML support `${VAR}` and `${VAR:-default}`:

```yaml
token: ${MM_TOKEN}            # required — raises ConfigError if unset
model: ${MODEL:-gpt-4o-mini}  # optional — falls back to gpt-4o-mini
```
