"""Application context passed through CLI commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from mattermind.config.models import AppConfig
from mattermind.ui.theme import CONSOLE


@dataclass
class AppContext:
    """Shared context for all CLI commands."""

    config: AppConfig | None = None
    config_path: Path | None = None
    console: Console = field(default_factory=lambda: CONSOLE)
    verbose: bool = False
    quiet: bool = False
    json_output: bool = False
    no_color: bool = False
