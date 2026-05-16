"""Interactive configuration wizard."""

from __future__ import annotations

from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax


def run_wizard(console: Console) -> Path:
    """Run an interactive wizard to create a config file.

    Returns the path of the written config file.
    """
    console.print(Panel("[bold cyan]Mattermind Setup Wizard[/bold cyan]", expand=False))
    console.print("\nThis wizard will create a config file at [bold]~/.config/mattermind/config.yaml[/bold]\n")

    # --- Mattermost ---
    console.print("[bold]Mattermost Settings[/bold]")
    mm_url = Prompt.ask(
        "  Mattermost URL",
        default="https://mm.company.com",
        console=console,
    ).rstrip("/")
    mm_team = Prompt.ask("  Team name (slug)", console=console)

    use_token = Confirm.ask("  Authenticate with a Personal Access Token (PAT)?", default=True, console=console)
    mm_section: dict[str, object]
    if use_token:
        mm_token = Prompt.ask("  Personal Access Token (PAT)", password=True, console=console)
        mm_section = {
            "url": mm_url,
            "token": mm_token,
            "team": mm_team,
            "timeout_seconds": 30,
            "rate_limit_rps": 10,
        }
    else:
        mm_login = Prompt.ask("  Login (email or username)", console=console)
        mm_password = Prompt.ask("  Password", password=True, console=console)
        mm_section = {
            "url": mm_url,
            "login": mm_login,
            "password": mm_password,
            "team": mm_team,
            "timeout_seconds": 30,
            "rate_limit_rps": 10,
        }

    # --- LLM ---
    console.print("\n[bold]LLM Settings[/bold]")
    llm_base_url = Prompt.ask(
        "  LLM base URL",
        default="https://api.openai.com/v1",
        console=console,
    ).rstrip("/")
    llm_api_key = Prompt.ask("  LLM API key", password=True, console=console)
    llm_model = Prompt.ask("  Model name", default="gpt-4o-mini", console=console)

    config: dict[str, object] = {
        "mattermost": mm_section,
        "llm": {
            "base_url": llm_base_url,
            "api_key": llm_api_key,
            "model": llm_model,
            "temperature": 0.2,
            "max_tokens_per_response": 4000,
            "request_timeout_seconds": 120,
        },
        "agent": {
            "max_iterations": 15,
            "max_threads_per_query": 20,
            "max_link_depth": 2,
            "total_token_budget": 200000,
            "parallel_tool_calls": True,
        },
        "output": {
            "show_thread_tree": True,
            "show_token_usage": True,
            "show_timings": True,
            "format": "markdown",
        },
        "logging": {
            "level": "INFO",
        },
    }

    yaml_text = yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)

    console.print("\n[bold]Preview:[/bold]")
    console.print(Syntax(yaml_text, "yaml", theme="monokai", line_numbers=False))

    target = Path.home() / ".config" / "mattermind" / "config.yaml"
    save = Confirm.ask(f"\n  Save to [bold]{target}[/bold]?", default=True, console=console)

    if not save:
        console.print("[yellow]Aborted. No file written.[/yellow]")
        raise SystemExit(0)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml_text, encoding="utf-8")

    console.print(f"\n[green]Config saved to {target}[/green]")
    console.print("[dim]You can also use environment variables; see .env.example for reference.[/dim]")

    return target
