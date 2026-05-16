"""Rich rendering helpers for mattermind output."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from mattermind.models import AskResult

# ------------------------------------------------------------------ #
# Banner                                                              #
# ------------------------------------------------------------------ #

_BANNER_LINES = [
    " ███╗   ███╗ █████╗ ████████╗████████╗███████╗██████╗ ",
    " ████╗ ████║██╔══██╗╚══██╔══╝╚══██╔══╝██╔════╝██╔══██╗",
    " ██╔████╔██║███████║   ██║      ██║   █████╗  ██████╔╝",
    " ██║╚██╔╝██║██╔══██║   ██║      ██║   ██╔══╝  ██╔══██╗",
    " ██║ ╚═╝ ██║██║  ██║   ██║      ██║   ███████╗██║  ██║",
    " ╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═╝",
    "                                                        ",
    "  ███╗   ███╗██╗███╗   ██╗██████╗                      ",
    "  ████╗ ████║██║████╗  ██║██╔══██╗                     ",
    "  ██╔████╔██║██║██╔██╗ ██║██║  ██║                     ",
    "  ██║╚██╔╝██║██║██║╚██╗██║██║  ██║                     ",
    "  ██║ ╚═╝ ██║██║██║ ╚████║██████╔╝                     ",
    "  ╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═════╝                      ",
]

_GRADIENT = ["bold cyan", "cyan", "bold blue", "blue", "bold magenta", "magenta"]


def render_banner(console: Console) -> None:
    """Render ASCII art banner with a colour gradient."""
    text = Text()
    for i, line in enumerate(_BANNER_LINES):
        style = _GRADIENT[i % len(_GRADIENT)]
        text.append(line + "\n", style=style)
    console.print(text)
    console.print("[muted]  Ask questions about your Mattermost workspace\n[/muted]")


# ------------------------------------------------------------------ #
# Query panel                                                         #
# ------------------------------------------------------------------ #


def render_query_panel(console: Console, query: str) -> None:
    """Render a panel showing the user's question."""
    console.print(
        Panel(
            Text(query, style="bold white"),
            title="[primary]Question[/primary]",
            border_style="secondary",
            expand=False,
            padding=(0, 2),
        )
    )


# ------------------------------------------------------------------ #
# Answer                                                              #
# ------------------------------------------------------------------ #


def render_answer(console: Console, markdown_text: str, fmt: str = "markdown") -> None:
    """Render the final LLM answer in the chosen format."""
    if fmt == "json":
        # Already handled by caller via AskResult.model_dump_json()
        return
    if fmt == "plain":
        console.print(markdown_text)
        return
    # Default: markdown
    console.print(
        Panel(
            Markdown(markdown_text),
            title="[primary]Answer[/primary]",
            border_style="primary",
            padding=(1, 2),
        )
    )


# ------------------------------------------------------------------ #
# Thread tree                                                         #
# ------------------------------------------------------------------ #


def render_thread_tree(
    console: Console,
    explored_threads: list[dict[str, str]],
) -> None:
    """Render a rich tree listing every explored thread with clickable links."""
    if not explored_threads:
        return

    root = Tree("[bold]Threads explored[/bold]", guide_style="muted")

    for thread in explored_threads:
        permalink = thread.get("permalink", "")
        channel = thread.get("channel", "unknown")
        title = thread.get("title", "")[:60] or "(no title)"

        label = Text()
        label.append(f"#{channel}  ", style="secondary")
        if permalink:
            label.append(title, style=f"link {permalink}")
        else:
            label.append(title)

        root.add(label)

    console.print(root)


# ------------------------------------------------------------------ #
# Summary                                                             #
# ------------------------------------------------------------------ #


def render_summary(console: Console, result: AskResult, show_tokens: bool = True, show_timings: bool = True) -> None:
    """Render a compact summary panel with run statistics."""
    table = Table.grid(padding=(0, 2))
    table.add_column(style="muted", justify="right")
    table.add_column()

    table.add_row("Threads explored", str(result.threads_explored))
    table.add_row("Tool calls", str(result.tool_calls_made))

    if show_tokens:
        table.add_row(
            "Tokens",
            f"prompt={result.token_usage.prompt_tokens}  "
            f"completion={result.token_usage.completion_tokens}  "
            f"total={result.token_usage.total_tokens}",
        )

    if show_timings:
        table.add_row("Elapsed", f"{result.elapsed_seconds:.1f}s")

    if result.incomplete:
        table.add_row("[warning]Status[/warning]", "[warning]incomplete (budget/limit reached)[/warning]")

    console.print(
        Panel(
            table,
            title="[muted]Run summary[/muted]",
            border_style="muted",
            expand=False,
            padding=(0, 1),
        )
    )


# ------------------------------------------------------------------ #
# Status line                                                         #
# ------------------------------------------------------------------ #


def render_status(console: Console, message: str) -> None:
    """Print a muted status line (used outside of live context)."""
    console.print(f"[muted]  {message}[/muted]")
