"""Beautiful error rendering via Rich panels."""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


def error_panel(
    console: Console,
    title: str,
    message: str,
    hint: str | None = None,
) -> None:
    """Render a red error panel with an optional hint line."""
    body = Text()
    body.append(message, style="bold white")
    if hint:
        body.append("\n\n")
        body.append("Hint: ", style="yellow bold")
        body.append(hint, style="yellow")

    console.print(
        Panel(
            body,
            title=f"[error] {title}[/error]",
            border_style="error",
            expand=False,
            padding=(1, 2),
        )
    )
