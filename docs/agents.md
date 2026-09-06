# mattermind for AI agents

> One page holding everything a coding assistant needs to configure, drive and embed
> mattermind correctly, plus a map of where the rest of the documentation keeps the
> details it leaves out. Give an agent this page rather than the whole site.

| | |
|---|---|
| Package | `mattermind` on PyPI, import root `mattermind` |
| Requires | Python 3.12+, a Mattermost server with REST API v4, an OpenAI-compatible chat-completions endpoint that supports tool calling |
| Install | `uv tool install mattermind`, or `pip install mattermind`. The `dev` and `docs` extras are for working on the project, not for using it |
| Command line | `mattermind ask`, `chat`, `teams`, `login`, `init`, `config show`, `config validate`, `version` |
| Python | async only — `AgentLoop` over `MattermostClient`, both driven with `await`; the CLI is a thin `asyncio.run` around them |
| Config | `~/.config/mattermind/config.yaml`, `MATTERMIND_*` environment variables, per-command flags |
| Source | <https://github.com/bedrock-python/mattermind> |

## How to read this page

Every page of this site is also served as raw Markdown at its own URL with `.md` in place
of the trailing slash — this page is `/agents.md`, the configuration guide is
`/guide/configuration.md` — so anything the map below points at can be fetched as plain
text rather than scraped out of HTML. The **Copy page** control at the top of a page does
the same thing for a human with a chat window open. The one exception is the API
reference: its Markdown is a list of instructions to a docstring renderer rather than the
API, so it carries neither the control nor a `.md` twin — read it as HTML, or read the
docstrings in the source.

Top to bottom before writing code or a command line.
[Rules that hold or break the code](#rules-that-hold-or-break-the-code) is the section
correctness lives in — those are the things mattermind will not save you from. Every name
used below exists in the package at this version; if you need something not listed here,
fetch the page the [documentation map](#documentation-map) points at rather than guessing
a flag or a method that sounds plausible.

## Scope

**It does** take one natural-language question, search one Mattermost team over REST API
v4, read whole threads, follow permalinks it finds inside messages, and return a markdown
answer in which every claim carries a permalink citation. It ships a Rich terminal
renderer, a Textual TUI (`mattermind chat`), a machine-readable JSON mode, and a config
loader that merges a YAML file, environment variables and command-line flags.

**It does not** index, cache or store anything — every run starts from a fresh search; it
reads only what the credential you give it can already read; it searches exactly one team
per run; it never writes to Mattermost — no posting, editing, reacting or deleting; it
ships no model and no API key; it runs no scheduler and no server. The package is 0.x and
classified Alpha: the importable surface is documented but still moving.

## Mental model

* **`AppConfig`** is the whole configuration as one validated Pydantic model, with
  `mattermost`, `llm`, `agent`, `output` and `logging` sections. `load_config()` builds it
  by merging, lowest priority first: model defaults, the YAML file, `MATTERMIND_*`
  environment variables, then an explicit overrides dict — which is what CLI flags become.
* **`MattermostClient`** is an async context manager over REST API v4. It authenticates
  with a token, or logs in with login and password on `__aenter__` and keeps the session
  token the server returns. It retries, and bounds how many requests are in flight.
* **`AgentLoop.run(question)`** is the loop: call the LLM with the system prompt, the
  question and four tool definitions; if the reply asks for tools, run them (in parallel by
  default), append the results and call again; stop when the model replies with text
  instead of tool calls, when the iteration limit is reached, or when the token budget is
  spent.
* **The four tools** are `mm_search`, `mm_get_thread`, `mm_resolve_permalink` and
  `mm_get_user`. They are the model's only access to Mattermost, and none of them writes.
* **`AgentState`** carries one run's mutable facts: which posts have been fetched, the
  running token count, the counters and the explored-thread list.
* **`AskResult`** is what a run returns, and exactly what `--json` prints.

The flow is: question → search variants → threads → permalinks inside those threads → more
threads → an answer whose every line links back to a post.

## Wiring

The command line is the intended entry point.

```bash
uv tool install mattermind

mattermind init                                    # writes ~/.config/mattermind/config.yaml
mattermind teams                                   # lists teams, saves the one you pick
mattermind ask "what was decided about the auth service migration?"

mattermind --json ask "latest incidents?" | jq -r .answer
```

Embedding it in Python is three objects — config, client, loop:

```python
import asyncio

from rich.console import Console

from mattermind.agent import AgentLoop
from mattermind.config import load_config
from mattermind.mattermost import MattermostClient


async def ask(question: str) -> str:
    config = load_config()                          # file + env; pass config_path= for a file
    async with MattermostClient(config.mattermost) as client:
        loop = AgentLoop(config=config, client=client, console=Console(), verbose=False)
        result = await loop.run(question, on_status=print)
    if result.incomplete:
        raise RuntimeError(f"stopped early after {result.tool_calls_made} tool calls")
    return result.answer


print(asyncio.run(ask("who owns billing?")))
```

`on_status` is optional and takes a single string; it is called on every phase change
("Connecting to Mattermost...", "Thinking... (iteration 3)", "Calling tools: mm_search",
"Answer ready."). `console` is used only for the `verbose=True` tool-call trace.

## The command line

| Command | What it does |
|---|---|
| `mattermind ask QUERY` | Runs the agent loop and renders the answer. Accepts `--mm-url`, `--mm-token`, `--mm-login`, `--mm-password`, `--team`, `--llm-base-url`, `--llm-api-key`, `--model` as per-run overrides |
| `mattermind chat` | Launches the Textual TUI. `ctrl+l` clears, `ctrl+t` toggles the thread panel, `ctrl+a` the activity log, `escape` cancels the running query, `ctrl+c` quits |
| `mattermind teams` | Lists the teams the credential can see and writes the chosen one to `mattermost.team` in the config file. Takes the four `--mm-*` overrides |
| `mattermind login [--mm-url URL]` | Prompts for an `MMAUTHTOKEN` and writes it as `mattermost.token`, removing any `login` and `password` beside it |
| `mattermind init` | Interactive wizard; writes `~/.config/mattermind/config.yaml` and overwrites what is there |
| `mattermind config show` | Prints the resolved configuration with the token and API key truncated to five characters |
| `mattermind config validate` | Validates the configuration, then checks both endpoints — `GET /api/v4/users/me` on Mattermost and `GET /models` on the LLM base URL. Exits 1 if either check fails |
| `mattermind version` | Prints the version |

Global flags, declared both on the application callback and on every command, so they are
accepted **before or after the subcommand**:

| Flag | Effect |
|---|---|
| `--config PATH`, `-c` | Read this YAML file instead of `~/.config/mattermind/config.yaml`. Also the file `teams` and `login` write back to |
| `--verbose`, `-v` | Print each tool call and the first 200 characters of each tool result, and a full traceback on an unexpected error |
| `--quiet`, `-q` | Print the answer as plain text and nothing else — no banner, no query panel, no status lines, no thread tree, no summary |
| `--json` | Print the result as JSON instead of rendering it |
| `--no-color` | Disable ANSI colour |

Exit codes:

| Code | Meaning |
|---|---|
| 0 | The command finished |
| 1 | The configuration is invalid, the run raised, or a `config validate` connectivity check failed |
| 2 | Usage — an unknown option, a missing argument, or no command at all |
| 130 | `Ctrl-C` during `ask` or `init` |

## Configuration

Priority, lowest first: model defaults, the YAML file, `MATTERMIND_*` environment
variables, then command-line flags. Every string value in the file supports `${VAR}` and
`${VAR:-default}`.

```yaml
mattermost:
  url: https://mm.company.com    # required
  token: ${MM_TOKEN}             # or login + password, never both
  team: engineering
  timeout_seconds: 30
  rate_limit_rps: 10
  verify_ssl: true

llm:
  base_url: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}     # required
  model: gpt-4o-mini
  temperature: 0.2
  max_tokens_per_response: 4000
  request_timeout_seconds: 120
  verify_ssl: true

agent:
  max_iterations: 15
  max_threads_per_query: 20
  max_link_depth: 2
  total_token_budget: 200000
  parallel_tool_calls: true

output:
  show_thread_tree: true
  show_token_usage: true
  show_timings: true
  format: markdown               # markdown | plain | json

logging:
  level: INFO                    # DEBUG | INFO | WARNING | ERROR | CRITICAL
```

| Section | Field | Default | Notes |
|---|---|---|---|
| `mattermost` | `url` | required | Trailing slashes are stripped |
| | `token` | `None` | A personal access token or an `MMAUTHTOKEN` cookie value |
| | `login` / `password` | `None` | The alternative to `token`; both must be set together |
| | `team` | `None` | A team slug or a team id. `ask` and `chat` need it |
| | `timeout_seconds` | `30` | Per HTTP request |
| | `rate_limit_rps` | `10` | Concurrent in-flight requests, not a per-second rate |
| | `verify_ssl` | `True` | `false` for a self-signed certificate |
| `llm` | `base_url` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint |
| | `api_key` | required | |
| | `model` | `gpt-4o-mini` | Must support tool calling |
| | `temperature` | `0.2` | |
| | `max_tokens_per_response` | `4000` | Per LLM call |
| | `request_timeout_seconds` | `120` | |
| | `verify_ssl` | `True` | |
| `agent` | `max_iterations` | `15` | Enforced: LLM calls per run |
| | `max_threads_per_query` | `20` | Enforced: successful `mm_get_thread` calls per run |
| | `max_link_depth` | `2` | Enforced: how many permalink hops from a search hit `mm_get_thread` will follow — see rule 7 |
| | `total_token_budget` | `200000` | Checked after each LLM call |
| | `parallel_tool_calls` | `True` | Run one round of tool calls concurrently |
| `output` | `show_thread_tree` | `True` | Print the explored-thread tree between the answer and the summary |
| | `show_token_usage` | `True` | Token row in the summary panel |
| | `show_timings` | `True` | Elapsed row in the summary panel |
| | `format` | `markdown` | `markdown`, `plain` or `json`; `json` prints the same body as `--json`. Any other value is a configuration error |
| `logging` | `level` | `INFO` | Applied to the root logger by `ask`, `teams` and `config validate`. Case-insensitive; an unknown level is a configuration error |

Environment variables, each overriding the same key in the file:

| Variable | Key |
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

## The tools the model is given

Four, defined in `mattermind.agent.tools.TOOL_DEFINITIONS` and dispatched by
`execute_tool`. Every one returns a JSON string, and every failure comes back as
`{"error": "..."}` rather than raising into the loop.

| Tool | Arguments | Returns |
|---|---|---|
| `mm_search` | `query` (required), `channel`, `since`, `limit` (default 20, capped at 60) | `{"results": [{post_id, message, channel_name, user_id, username, permalink}], "count": n}`. `message` is truncated to 500 characters |
| `mm_get_thread` | `post_id` | `{"root_post_id", "post_count", "posts": [{post_id, user_id, message, created_at, permalink}]}`, posts ascending by creation time |
| `mm_resolve_permalink` | `url` | `{"post_id": "..."}`, parsed from `/pl/<id>` in the URL |
| `mm_get_user` | `user_id` | `{"user_id", "username", "display_name"}` |

`channel` and `since` are not separate API parameters: they are appended to the search
terms as `in:<channel>` and `after:<date>`, so they follow Mattermost's own search syntax.
`mm_get_thread` refuses a post it has already fetched, refuses a post more than
`max_link_depth` permalink hops from a search hit, and refuses everything once
`max_threads_per_query` threads have been read — the last refusal sets `incomplete`.

## The Python surface

`import mattermind` gives you `__version__` and nothing else. Everything below is imported
from the submodule that declares it.

`mattermind.config`

| Name | Signature | Returns |
|---|---|---|
| `load_config` | `load_config(config_path: Path | None = None, overrides: dict | None = None)` | `AppConfig` |
| `ConfigError` | exception | |
| `AppConfig` | `mattermost`, `llm`, `agent`, `output`, `logging` | |
| `MattermostConfig`, `LLMConfig`, `AgentConfig`, `OutputConfig`, `LoggingConfig` | the sections above | |

`mattermind.mattermost`

| Name | Signature | Returns |
|---|---|---|
| `MattermostClient` | `MattermostClient(config: MattermostConfig)`, used as `async with` | |
| `.get_my_teams()` | | `list[Team]` |
| `.get_team_id(team_name_or_id)` | | `str` — tries the name endpoint, falls back to the id endpoint on 404 |
| `.search_posts(team_id, query, channel_id=None, per_page=20)` | | `list[SearchHit]` |
| `.get_thread(post_id)` | | `Thread` |
| `.get_user(user_id)` | | `User` |
| `.get_channel(channel_id)` | | `dict[str, str]` of the raw channel payload |
| `.permalink(post_id)` | | `str` — `{url}/{team}/pl/{post_id}`, or `""` when `mattermost.team` is unset |
| `.validate_connection()` | | `bool` — `GET /users/me` succeeded |
| `Post` | `id`, `create_at` (ms epoch), `user_id`, `channel_id`, `message`, `root_id` | `.created_at` is an aware UTC `datetime` |
| `Thread` | `root_post_id`, `posts` | ascending by `create_at` |
| `SearchHit` | `post_id`, `message`, `channel_id`, `channel_name`, `user_id`, `username`, `permalink` | `search_posts` fills both; `permalink` is empty when `mattermost.team` is unset — see rule 11 |
| `User` | `id`, `username`, `first_name`, `last_name`, `nickname`, `position` | `.display_name` is full name, else nickname, else username |

`Team` lives in `mattermind.mattermost.models` and `MattermostAPIError` in
`mattermind.mattermost.client`; neither is re-exported from the package — see rule 16.

`mattermind.agent`

| Name | Signature | Returns |
|---|---|---|
| `AgentLoop` | `AgentLoop(config: AppConfig, client: MattermostClient, console: Console, verbose: bool = False)` | |
| `.run(question, on_status=None)` | `on_status: Callable[[str], None] | None` | `AskResult` |
| `AgentState` | dataclass: `visited_post_ids`, `link_depth`, `channel_names`, `token_usage`, `threads_fetched`, `tool_calls_made`, `explored_threads`, `incomplete` | |

`mattermind.agent.tools` adds `TOOL_DEFINITIONS`, `execute_tool(...)` and
`parse_post_id_from_permalink(url) -> str | None`; `mattermind.agent.prompts` adds
`SYSTEM_PROMPT`, a template with one `{max_depth}` placeholder.

`mattermind.models`

| Name | Fields |
|---|---|
| `AskResult` | `answer: str`, `threads_explored: int`, `tool_calls_made: int`, `token_usage: TokenUsage`, `elapsed_seconds: float`, `incomplete: bool = False`, `permalinks: list[str] = []`, `explored_threads: list[dict[str, str]] = []` (`post_id`, `channel`, `title`, `permalink` per thread read) |
| `TokenUsage` | `prompt_tokens`, `completion_tokens`, `total_tokens`, all `int` and all defaulting to 0; `.add(other)` returns a new instance |

`mattermind.ui` exports `CONSOLE` and `THEME`; `mattermind.ui.tui` exports `MattermindApp`
and `run_tui(config_path=None)`; `mattermind.ui.renderer` holds the Rich helpers the CLI
prints with.

## Rules that hold or break the code

1. **Global flags go on either side of the subcommand.** `--config`, `--verbose`,
   `--quiet`, `--json` and `--no-color` are declared on the application callback and on
   every command, so `mattermind --json ask "..."` and `mattermind ask "..." --json` are
   the same command. Given on both sides, a switch is simply on, and the `--config` after
   the subcommand wins.
2. **`--quiet` prints the answer as plain text, and nothing else.** No banner, no query
   panel, no status lines, no thread tree, no run summary — and no Rich markdown panel
   either, so it pipes cleanly. `mattermind --json ask "..." | jq -r .answer` is the
   machine-readable alternative.
3. **Exactly one authentication method.** A token, or a login and a password; both present
   is an error, neither is an error. Environment variables merge *on top of* the file, so
   `MATTERMIND_MM_TOKEN` set against a file that carries `login` and `password` makes the
   configuration invalid rather than overriding it. `mattermind login` removes the pair
   when it writes a token, which is the safe way to switch.
4. **Unknown configuration keys are rejected.** Every config model sets
   `extra="forbid"`, so a misspelled key fails validation with the key named in the error
   instead of being dropped. The same holds for a bad `output.format` or `logging.level`
   value. `mattermind config show` is how you check what actually loaded.
5. **A broken default config file is swallowed; a broken `--config` file is not.** With no
   `--config`, an unparseable `~/.config/mattermind/config.yaml` is ignored and the run
   continues on environment variables alone. With `--config PATH`, a missing or unparseable
   file raises `ConfigError`.
6. **`rate_limit_rps` is a concurrency limit, not a rate.** It sizes an
   `asyncio.Semaphore` around in-flight requests; nothing measures requests per second.
7. **`max_link_depth` is enforced, not just prompted.** A search hit is depth 0; every
   permalink found inside a fetched thread is recorded one level deeper in
   `AgentState.link_depth`. `mm_get_thread` refuses a post whose recorded depth exceeds
   `max_link_depth` and tells the model why. A post nothing has linked to counts as depth
   0, so a permalink the model brings in from elsewhere is never refused on arrival.
   `max_iterations` and `max_threads_per_query` are enforced too, in the loop and in
   `mm_get_thread` respectively.
8. **The token budget is checked after each LLM call, not before.** Crossing it prompts on
   stdin — `Continue beyond token budget? [y/N]:` — under every output mode, `--json`
   included. Answering no ends the run with `incomplete=True`. Answering yes raises the
   budget on the live `AppConfig` and keeps going.
9. **An incomplete run still returns an `AskResult`, and its `answer` can be empty.** Both
   an exhausted budget and an exhausted iteration count set `incomplete=True` with no final
   assistant message to fall back on. Check `incomplete` before you trust `answer`.
10. **`MattermostClient` only works inside `async with`.** Constructed and called directly,
    every method raises `RuntimeError`; login/password authentication happens in
    `__aenter__` and never otherwise.
11. **A search hit is citable, unless `team` is unset.** `search_posts` fills
    `permalink` as `{mattermost.url}/{mattermost.team}/pl/{post_id}` and `username` from
    one `GET /users/{id}` per distinct author in the page of results. With no
    `mattermost.team` configured the permalink is `""` rather than a URL with a hole in
    it; an author the server will not return leaves `username` empty. `client.permalink()`
    builds the same URL for a post id you already hold.
12. **`mattermost.team` must be set for `ask` and `chat`.** `AgentLoop.run` raises
    `ValueError` before the first LLM call if it is missing. `mattermind teams` is the way
    to set it.
13. **The agent reads exactly what the credential reads.** Search runs as the authenticated
    user against one team; a channel that user cannot see does not exist as far as the
    answer is concerned, and nothing in the output says so.
14. **`output.format: json` and `--json` print the same body.** Setting the file to
    `json` makes every `ask` machine-readable without the flag; `markdown` and `plain`
    render the answer, and `--quiet` overrides both with plain text. `show_thread_tree`
    prints the tree of threads the run read, built from `AskResult.explored_threads`.
15. **`logging.level` is applied by the commands that do work.** `ask`, `teams` and
    `config validate` call `logging.basicConfig` with it, writing to stderr; `chat` does
    not, because log lines would corrupt the TUI. `--verbose` prints tool calls to the
    console, it does not raise the log level.
16. **Import a name from the module that declares it.** The project runs mypy with
    `implicit_reexport = false`, and `Team` and `MattermostAPIError` are absent from
    `mattermind.mattermost.__all__` — import them from `mattermind.mattermost.models` and
    `mattermind.mattermost.client`.
17. **Retries cover 429 and 5xx only.** Three attempts, exponential backoff between one and
    eight seconds, also on connect, timeout and remote-protocol errors. Every other 4xx
    raises `MattermostAPIError` on the first response.
18. **`AgentLoop` mutates the `AppConfig` it was handed** when a budget overrun is
    confirmed. Give concurrent runs their own config object.

## Common mistakes

```bash
# WRONG — scraping the answer out of the rendered panel
mattermind ask "who owns billing?" | sed -n '/Answer/,$p'

# RIGHT — the answer as text, or as JSON
mattermind ask "who owns billing?" --quiet
mattermind ask "who owns billing?" --json | jq -r .answer
```

```yaml
# WRONG — a misspelled key is now a configuration error, not a silent default
agent:
  max_iteration: 30

# RIGHT
agent:
  max_iterations: 30
```

```yaml
# WRONG — both authentication methods present, so the configuration is refused
mattermost:
  url: https://mm.company.com
  login: me@company.com
  password: ${MM_PASSWORD}
  token: ${MM_TOKEN}
```

```yaml
# RIGHT — one of them
mattermost:
  url: https://mm.company.com
  token: ${MM_TOKEN}
  team: engineering
```

```python
# WRONG — the client outside its context manager: every call raises RuntimeError
client = MattermostClient(config.mattermost)
hits = await client.search_posts(team_id, "incident")

# RIGHT — and a search hit already carries the permalink to cite
async with MattermostClient(config.mattermost) as client:
    team_id = await client.get_team_id(config.mattermost.team)
    hits = await client.search_posts(team_id, "incident")
    cite(hits[0].permalink)                   # "" only when mattermost.team is unset
```

```python
# WRONG — trusting the answer of a run that stopped early
result = await AgentLoop(config, client, console).run(question)
publish(result.answer)

# RIGHT
result = await AgentLoop(config, client, console).run(question)
if result.incomplete or not result.answer:
    log.warning("stopped early after %d tool calls", result.tool_calls_made)
else:
    publish(result.answer)
```

## Errors

| Exception | Where from | Means |
|---|---|---|
| `ConfigError` (`mattermind.config`) | `load_config` | The file is missing or unparseable, a `${VAR}` has no value and no default, or the merged document failed validation. The CLI renders it as a panel and exits 1 |
| `MattermostAPIError` (`mattermind.mattermost.client`) | every client method | Mattermost answered 4xx or 5xx; `.status_code` carries it. A successful login that returned no `Token` header raises it with `status_code` 0 |
| `ValueError` | `AgentLoop.run` | `mattermost.team` is not set |
| `RuntimeError` | `MattermostClient` | Used outside `async with` |
| `pydantic.ValidationError` | constructing a config model directly | `load_config` catches this one and re-raises `ConfigError` with a readable list of field errors |

Everything the OpenAI SDK raises — authentication, rate limit, timeout — passes through
`AgentLoop.run` unchanged. The four tools are the exception: `execute_tool` catches every
exception and hands the model `{"error": "..."}`, so a failing tool slows a run down rather
than ending it.

## Documentation map

Fetch a page when the task is the one named beside it.

| Page | Read it when |
|---|---|
| [Home](index.md) | what mattermind is and the shape of one run |
| [Quickstart](guide/quickstart.md) | installing it and getting the first answer out |
| [Configuration](guide/configuration.md) | the config file, environment variables, interpolation |
| [Commands](guide/commands.md) | which command does what, and its flags |
| [Output modes](guide/output.md) | the JSON schema, quiet and no-colour output |
| [API reference](reference/index.md) | an exact signature, field or docstring — HTML only, see above |
| [Changelog](changelog.md) | what changed between versions |
