"""Rich theme and shared console instance."""

from rich.console import Console
from rich.theme import Theme

THEME = Theme(
    {
        "primary": "bold cyan",
        "secondary": "blue",
        "muted": "dim",
        "success": "green",
        "warning": "yellow",
        "error": "bold red",
        "highlight": "bold magenta",
        "code": "bright_black on grey11",
        "link": "underline blue",
    }
)

CONSOLE = Console(theme=THEME)
