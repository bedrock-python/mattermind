"""Typer CLI application for mattermind."""

import asyncio
import logging
import sys
import traceback
from pathlib import Path
from typing import Annotated, Any

import httpx
import orjson
import typer
import yaml
from openai import AsyncOpenAI
from rich.console import Console
from rich.prompt import IntPrompt, Prompt
from rich.table import Table

from mattermind.__version__ import __version__
from mattermind.agent.loop import AgentLoop
from mattermind.cli.context import AppContext
from mattermind.config.loader import ConfigError, load_config
from mattermind.config.models import AppConfig
from mattermind.config.wizard import run_wizard
from mattermind.mattermost.client import MattermostClient
from mattermind.models import AskResult
from mattermind.ui.errors import error_panel
from mattermind.ui.renderer import (
    render_answer,
    render_banner,
    render_query_panel,
    render_status,
    render_summary,
    render_thread_tree,
)
from mattermind.ui.theme import CONSOLE, THEME

# ------------------------------------------------------------------ #
# Typer app                                                           #
# ------------------------------------------------------------------ #

app = typer.Typer(
    name="mattermind",
    help="Ask natural-language questions about your Mattermost workspace.",
    add_completion=False,
    pretty_exceptions_enable=False,
    no_args_is_help=True,
)

config_app = typer.Typer(name="config", help="Configuration management commands.")
app.add_typer(config_app)

# Shared context object (populated by the callback and by every command)
_ctx = AppContext()

# ------------------------------------------------------------------ #
# Global flags                                                        #
# ------------------------------------------------------------------ #
# The same five options are declared on the application callback and on every
# command, so they are accepted both before and after the subcommand:
#     mattermind --json ask "..."
#     mattermind ask "..." --json

ConfigOption = Annotated[Path | None, typer.Option("--config", "-c", help="Path to config YAML file.")]
VerboseOption = Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")]
QuietOption = Annotated[bool, typer.Option("--quiet", "-q", help="Print the answer only, without the UI chrome.")]
JsonOption = Annotated[bool, typer.Option("--json", help="Output result as JSON (machine-readable).")]
NoColorOption = Annotated[bool, typer.Option("--no-color", help="Disable colour output.")]


def _apply_global_flags(
    config_path: Path | None = None,
    verbose: bool = False,
    quiet: bool = False,
    output_json: bool = False,
    no_color: bool = False,
) -> None:
    """Merge global flags into the shared context, wherever they were given."""
    if config_path is not None:
        _ctx.config_path = config_path
    _ctx.verbose = _ctx.verbose or verbose
    _ctx.quiet = _ctx.quiet or quiet
    _ctx.json_output = _ctx.json_output or output_json
    _ctx.no_color = _ctx.no_color or no_color

    # Keep the theme: the panels below print styles like "error" by name.
    _ctx.console = Console(no_color=True, theme=THEME) if _ctx.no_color else CONSOLE


def _configure_logging(level: str) -> None:
    """Apply ``logging.level`` from the configuration to the root logger."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )


def _get_console() -> Console:
    """Return the console to print with (respects --no-color)."""
    return _ctx.console


# ------------------------------------------------------------------ #
# Global callback                                                     #
# ------------------------------------------------------------------ #


@app.callback()
def main_callback(
    config: ConfigOption = None,
    verbose: VerboseOption = False,
    quiet: QuietOption = False,
    output_json: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Mattermind — ask questions about your Mattermost workspace."""
    _apply_global_flags(config, verbose, quiet, output_json, no_color)


# ------------------------------------------------------------------ #
# ask command                                                         #
# ------------------------------------------------------------------ #


@app.command()
def ask(
    query: Annotated[str, typer.Argument(help="Natural-language question to ask.")],
    mm_url: Annotated[str | None, typer.Option("--mm-url", help="Mattermost server URL.")] = None,
    mm_token: Annotated[str | None, typer.Option("--mm-token", help="Personal access token.")] = None,
    mm_login: Annotated[str | None, typer.Option("--mm-login", help="Mattermost login (email or username).")] = None,
    mm_password: Annotated[str | None, typer.Option("--mm-password", help="Mattermost password.")] = None,
    team: Annotated[str | None, typer.Option("--team", help="Mattermost team name.")] = None,
    llm_base_url: Annotated[str | None, typer.Option("--llm-base-url", help="LLM API base URL.")] = None,
    llm_api_key: Annotated[str | None, typer.Option("--llm-api-key", help="LLM API key.")] = None,
    model: Annotated[str | None, typer.Option("--model", help="LLM model name.")] = None,
    config_path: ConfigOption = None,
    verbose: VerboseOption = False,
    quiet: QuietOption = False,
    output_json: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Ask a question about your Mattermost workspace."""
    _apply_global_flags(config_path, verbose, quiet, output_json, no_color)
    console = _get_console()

    if not _ctx.quiet and not _ctx.json_output:
        render_banner(console)

    # Build overrides from CLI flags
    overrides: dict[str, Any] = {}
    if mm_url or mm_token or mm_login or mm_password or team:
        mm_ov: dict[str, str] = {}
        if mm_url:
            mm_ov["url"] = mm_url
        if mm_token:
            mm_ov["token"] = mm_token
        if mm_login:
            mm_ov["login"] = mm_login
        if mm_password:
            mm_ov["password"] = mm_password
        if team:
            mm_ov["team"] = team
        overrides["mattermost"] = mm_ov
    if llm_base_url or llm_api_key or model:
        llm_ov: dict[str, str] = {}
        if llm_base_url:
            llm_ov["base_url"] = llm_base_url
        if llm_api_key:
            llm_ov["api_key"] = llm_api_key
        if model:
            llm_ov["model"] = model
        overrides["llm"] = llm_ov

    try:
        config = load_config(config_path=_ctx.config_path, overrides=overrides)
    except ConfigError as exc:
        error_panel(
            console,
            "Configuration Error",
            str(exc),
            hint="Run `mattermind init` to set up your config interactively.",
        )
        raise typer.Exit(1) from exc

    _configure_logging(config.logging.level)

    if not _ctx.quiet and not _ctx.json_output:
        render_query_panel(console, query)

    try:
        result = asyncio.run(_run_ask(query, config, console))
    except KeyboardInterrupt:
        console.print("\n[warning]Interrupted.[/warning]")
        raise typer.Exit(130) from None
    except Exception as exc:
        if _ctx.verbose:
            traceback.print_exc()
        error_panel(console, "Unexpected Error", str(exc), hint="Run with --verbose for a full traceback.")
        raise typer.Exit(1) from exc

    if _ctx.json_output or config.output.format == "json":
        sys.stdout.write(result.model_dump_json(indent=2) + "\n")
        return

    # --quiet means the answer and nothing else.
    render_answer(console, result.answer, fmt="plain" if _ctx.quiet else config.output.format)

    if _ctx.quiet:
        return

    if config.output.show_thread_tree and result.explored_threads:
        console.print()
        render_thread_tree(console, result.explored_threads)

    render_summary(
        console,
        result,
        show_tokens=config.output.show_token_usage,
        show_timings=config.output.show_timings,
    )


async def _run_ask(
    question: str,
    config: AppConfig,
    console: Console,
) -> AskResult:
    """Async wrapper that runs the agent loop."""

    def on_status(msg: str) -> None:
        if not _ctx.quiet and not _ctx.json_output:
            render_status(console, msg)

    async with MattermostClient(config.mattermost) as mm_client:
        loop = AgentLoop(
            config=config,
            client=mm_client,
            console=console,
            verbose=_ctx.verbose,
        )
        return await loop.run(question, on_status=on_status)


# ------------------------------------------------------------------ #
# init command                                                        #
# ------------------------------------------------------------------ #


@app.command()
def teams(
    mm_url: Annotated[str | None, typer.Option("--mm-url", help="Mattermost server URL.")] = None,
    mm_token: Annotated[str | None, typer.Option("--mm-token", help="Personal access token.")] = None,
    mm_login: Annotated[str | None, typer.Option("--mm-login", help="Mattermost login.")] = None,
    mm_password: Annotated[str | None, typer.Option("--mm-password", help="Mattermost password.")] = None,
    config_path: ConfigOption = None,
    verbose: VerboseOption = False,
    quiet: QuietOption = False,
    output_json: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """List Mattermost teams available to the current user."""
    _apply_global_flags(config_path, verbose, quiet, output_json, no_color)
    console = _get_console()

    overrides: dict[str, Any] = {}
    if mm_url or mm_token or mm_login or mm_password:
        mm_ov: dict[str, str] = {}
        if mm_url:
            mm_ov["url"] = mm_url
        if mm_token:
            mm_ov["token"] = mm_token
        if mm_login:
            mm_ov["login"] = mm_login
        if mm_password:
            mm_ov["password"] = mm_password
        overrides["mattermost"] = mm_ov

    try:
        config = load_config(config_path=_ctx.config_path, overrides=overrides)
    except ConfigError as exc:
        error_panel(console, "Configuration Error", str(exc))
        raise typer.Exit(1) from exc

    _configure_logging(config.logging.level)

    try:
        result = asyncio.run(_run_teams(config))
    except Exception as exc:
        error_panel(console, "Error", str(exc))
        raise typer.Exit(1) from exc

    if _ctx.json_output:
        sys.stdout.write(orjson.dumps([t.model_dump() for t in result], option=orjson.OPT_INDENT_2).decode() + "\n")
        return

    table = Table(title="Your Mattermost Teams", show_lines=False)
    table.add_column("#", style="dim", no_wrap=True)
    table.add_column("Slug", style="cyan", no_wrap=True)
    table.add_column("Display name", style="bold")
    table.add_column("Type")
    table.add_column("Description")

    for i, team in enumerate(result, 1):
        team_type = "open" if team.type == "O" else "invite-only"
        table.add_row(str(i), team.name, team.display_name, team_type, team.description)

    console.print(table)

    if len(result) == 0:
        return

    # If there's only one team — select it automatically
    if len(result) == 1:
        chosen = result[0]
        console.print(f"[dim]Auto-selected the only team:[/dim] [cyan]{chosen.name}[/cyan]")
    else:
        idx = IntPrompt.ask(
            "Select team number to save to config",
            console=console,
            default=1,
        )
        if idx < 1 or idx > len(result):
            error_panel(console, "Error", f"Invalid selection: {idx}")
            raise typer.Exit(1)
        chosen = result[idx - 1]

    config_path = _ctx.config_path or Path.home() / ".config" / "mattermind" / "config.yaml"
    existing: dict[str, Any] = {}
    if config_path.exists():
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except Exception:
            pass

    mm_section = existing.get("mattermost", {})
    if not isinstance(mm_section, dict):
        mm_section = {}
    mm_section["team"] = chosen.name
    existing["mattermost"] = mm_section

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.dump(existing, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    console.print(f"[green]Team [bold]{chosen.name}[/bold] saved to {config_path}[/green]")


async def _run_teams(config: AppConfig) -> list[Any]:
    async with MattermostClient(config.mattermost) as mm_client:
        return await mm_client.get_my_teams()


@app.command()
def login(
    mm_url: Annotated[str | None, typer.Option("--mm-url", help="Mattermost server URL.")] = None,
    config_path: ConfigOption = None,
    verbose: VerboseOption = False,
    quiet: QuietOption = False,
    output_json: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Save a Mattermost session token to config.

    How to get your token:
    1. Open Mattermost in Chrome and log in via SSO.
    2. Open DevTools (F12) -> Application -> Cookies -> your MM domain.
    3. Copy the value of MMAUTHTOKEN.
    """
    _apply_global_flags(config_path, verbose, quiet, output_json, no_color)
    console = _get_console()

    console.print(
        "\n[bold]How to get your token:[/bold]\n"
        "  1. Open Mattermost in Chrome and log in via SSO\n"
        "  2. Press [bold]F12[/bold] → Application → Cookies → your MM domain\n"
        "  3. Copy the value of [bold cyan]MMAUTHTOKEN[/bold cyan]\n"
    )

    url = mm_url
    if not url:
        try:
            config = load_config(config_path=_ctx.config_path)
            url = config.mattermost.url
        except ConfigError:
            url = Prompt.ask("Mattermost URL", default="https://mm.company.com", console=console)

    token = Prompt.ask("Paste MMAUTHTOKEN value", password=True, console=console)
    if not token.strip():
        error_panel(console, "Error", "Token cannot be empty.")
        raise typer.Exit(1)

    config_path = _ctx.config_path or Path.home() / ".config" / "mattermind" / "config.yaml"

    existing: dict[str, object] = {}
    if config_path.exists():
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except Exception:
            pass

    mm_section = existing.get("mattermost", {})
    if not isinstance(mm_section, dict):
        mm_section = {}

    mm_section["token"] = token.strip()
    mm_section.pop("login", None)
    mm_section.pop("password", None)
    mm_section.setdefault("url", url)

    existing["mattermost"] = mm_section
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.dump(existing, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    console.print(f"\n[green]Token saved to {config_path}[/green]")
    console.print("[dim]Run [bold]mattermind teams[/bold] to verify the connection.[/dim]")


@app.command()
def init(
    config_path: ConfigOption = None,
    verbose: VerboseOption = False,
    quiet: QuietOption = False,
    output_json: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Interactively create a mattermind config file."""
    _apply_global_flags(config_path, verbose, quiet, output_json, no_color)
    console = _get_console()
    try:
        run_wizard(console)
    except KeyboardInterrupt:
        console.print("\n[warning]Aborted.[/warning]")
        raise typer.Exit(130) from None


# ------------------------------------------------------------------ #
# chat command (TUI)                                                  #
# ------------------------------------------------------------------ #


@app.command()
def chat(
    config_path: ConfigOption = None,
    verbose: VerboseOption = False,
    quiet: QuietOption = False,
    output_json: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Launch the interactive TUI chat interface."""
    from mattermind.ui.tui import run_tui

    _apply_global_flags(config_path, verbose, quiet, output_json, no_color)
    console = _get_console()

    try:
        run_tui(config_path=_ctx.config_path)
    except ConfigError as exc:
        error_panel(
            console,
            "Configuration Error",
            str(exc),
            hint="Run `mattermind init` to set up your config interactively.",
        )
        raise typer.Exit(1) from exc


# ------------------------------------------------------------------ #
# version command                                                     #
# ------------------------------------------------------------------ #


@app.command()
def version(
    config_path: ConfigOption = None,
    verbose: VerboseOption = False,
    quiet: QuietOption = False,
    output_json: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Print the mattermind version and exit."""
    _apply_global_flags(config_path, verbose, quiet, output_json, no_color)
    console = _get_console()
    console.print(f"mattermind [primary]{__version__}[/primary]")


# ------------------------------------------------------------------ #
# config sub-commands                                                 #
# ------------------------------------------------------------------ #


@config_app.command("show")
def config_show(
    config_path: ConfigOption = None,
    verbose: VerboseOption = False,
    quiet: QuietOption = False,
    output_json: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Print the resolved configuration (with secrets masked)."""
    _apply_global_flags(config_path, verbose, quiet, output_json, no_color)
    console = _get_console()

    try:
        config = load_config(config_path=_ctx.config_path)
    except ConfigError as exc:
        error_panel(console, "Configuration Error", str(exc))
        raise typer.Exit(1) from exc

    resolved_path = _ctx.config_path or Path.home() / ".config" / "mattermind" / "config.yaml"

    if _ctx.json_output:
        mm_safe: dict[str, object] = {"url": config.mattermost.url, "team": config.mattermost.team}
        if config.mattermost.token:
            mm_safe["token"] = config.mattermost.token[:5] + "***"
        else:
            mm_safe["login"] = config.mattermost.login
            mm_safe["password"] = "***"
        safe: dict[str, object] = {
            "config_path": str(resolved_path),
            "mattermost": mm_safe,
            "llm": {
                "base_url": config.llm.base_url,
                "api_key": config.llm.api_key[:5] + "***",
                "model": config.llm.model,
            },
        }
        sys.stdout.write(orjson.dumps(safe, option=orjson.OPT_INDENT_2).decode() + "\n")
        return

    console.print(f"[bold]Config file:[/bold] {resolved_path}")
    console.print(f"[bold]Mattermost:[/bold]  {config.mattermost}")
    console.print(f"[bold]LLM:[/bold]         {config.llm}")
    console.print(f"[bold]Agent:[/bold]       {config.agent}")
    console.print(f"[bold]Output:[/bold]      {config.output}")


@config_app.command("validate")
def config_validate(
    config_path: ConfigOption = None,
    verbose: VerboseOption = False,
    quiet: QuietOption = False,
    output_json: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Validate the configuration and check both endpoints are reachable."""
    _apply_global_flags(config_path, verbose, quiet, output_json, no_color)
    console = _get_console()

    try:
        config = load_config(config_path=_ctx.config_path)
    except ConfigError as exc:
        error_panel(console, "Invalid Configuration", str(exc))
        raise typer.Exit(1) from exc

    _configure_logging(config.logging.level)
    console.print("[success]Configuration is valid.[/success]")

    (mm_ok, mm_detail), (llm_ok, llm_detail) = asyncio.run(_check_endpoints(config))

    for label, ok, detail in (
        (f"Mattermost {config.mattermost.url}", mm_ok, mm_detail),
        (f"LLM {config.llm.base_url}", llm_ok, llm_detail),
    ):
        if ok:
            console.print(f"[success]OK[/success]      {label}")
        else:
            console.print(f"[error]FAILED[/error]  {label} — {detail}")

    if not (mm_ok and llm_ok):
        raise typer.Exit(1)


async def _check_endpoints(config: AppConfig) -> tuple[tuple[bool, str], tuple[bool, str]]:
    """Check Mattermost and the LLM endpoint in one event loop."""
    return await _check_mattermost(config), await _check_llm(config)


async def _check_mattermost(config: AppConfig) -> tuple[bool, str]:
    """Return whether Mattermost answers as the configured user."""
    try:
        async with MattermostClient(config.mattermost) as client:
            if await client.validate_connection():
                return True, ""
            return False, "the server is unreachable, or it rejected the credentials"
    except Exception as exc:
        return False, str(exc)


async def _check_llm(config: AppConfig) -> tuple[bool, str]:
    """Return whether the LLM endpoint answers a model listing."""
    llm = AsyncOpenAI(
        base_url=config.llm.base_url,
        api_key=config.llm.api_key,
        http_client=httpx.AsyncClient(
            verify=config.llm.verify_ssl,
            timeout=config.llm.request_timeout_seconds,
        ),
    )
    try:
        await llm.models.list()
    except Exception as exc:
        return False, str(exc)
    else:
        return True, ""
    finally:
        await llm.close()


# ------------------------------------------------------------------ #
# Entrypoint                                                          #
# ------------------------------------------------------------------ #


def main() -> None:
    """Entrypoint registered in pyproject.toml."""
    app()


if __name__ == "__main__":
    main()
