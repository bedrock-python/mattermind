"""Custom Textual widgets for the Mattermind TUI."""

from __future__ import annotations

import time
from datetime import datetime
from typing import ClassVar

from rich.markup import escape as markup_escape
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, Markdown, Static

# ------------------------------------------------------------------ #
# Message bubble                                                      #
# ------------------------------------------------------------------ #

_BANNER = """\
 ██╗   ██╗ █████╗ ████████╗████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗██████╗
 ███╗ ███║██╔══██╗╚══██╔══╝╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║██╔══██╗
 ██╔████╔██║███████║   ██║      ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║██║  ██║
 ██║╚██╔╝██║██╔══██║   ██║      ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║██║  ██║
 ██║ ╚═╝ ██║██║  ██║   ██║      ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║██████╔╝
 ╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═════╝"""


class MessageBubble(Widget):
    """A single chat message bubble (user or assistant)."""

    DEFAULT_CSS = """
    MessageBubble {
        layout: vertical;
        margin: 0 0 1 0;
        width: 1fr;
        height: auto;
    }
    """

    def __init__(
        self,
        role: str,
        content: str,
        ts: float | None = None,
        message_id: str | None = None,
    ) -> None:
        super().__init__(classes=role, id=message_id)
        self._role = role
        self._content = content
        self._ts = ts or time.time()

    def compose(self) -> ComposeResult:
        ts_str = datetime.fromtimestamp(self._ts).strftime("%H:%M")
        label = "You" if self._role == "user" else "Mattermind"
        yield Static(f"{label}  {ts_str}", classes="bubble-header")
        if self._role == "assistant":
            yield Markdown(self._content, classes="bubble-body")
        else:
            yield Static(self._content, classes="bubble-body")

    def update_content(self, content: str) -> None:
        """Refresh content in an existing bubble (streaming)."""
        self._content = content
        try:
            body = self.query_one(".bubble-body")
            if self._role == "assistant":
                assert isinstance(body, Markdown)
                body.update(content)
            else:
                assert isinstance(body, Static)
                body.update(content)
        except Exception:
            pass


# ------------------------------------------------------------------ #
# Agent activity log                                                  #
# ------------------------------------------------------------------ #

_MAX_ACTIVITY_LINES = 120


class AgentActivityLog(Widget):
    """Scrollable log of agent tool calls and status messages."""

    DEFAULT_CSS = """
    AgentActivityLog {
        height: 8;
        overflow-y: auto;
        scrollbar-size: 0 0;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="activity-log")
        self._lines: list[tuple[str, str]] = []  # (text, css_class)

    def compose(self) -> ComposeResult:
        yield Static("● Agent activity", id="activity-title")

    def add_line(self, text: str, kind: str = "info") -> None:
        """Append a status line. kind: 'info' | 'tool' | 'done' | 'error'."""
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"  {ts}  {text}"
        self._lines.append((entry, kind))
        if len(self._lines) > _MAX_ACTIVITY_LINES:
            self._lines.pop(0)

        label = Label(markup_escape(entry), classes=f"activity-line {kind}")
        self.mount(label)
        self.scroll_end(animate=False)


# ------------------------------------------------------------------ #
# Thread explorer                                                     #
# ------------------------------------------------------------------ #


class ThreadItem(Widget):
    """A single explored-thread entry in the side panel."""

    def __init__(self, channel: str, title: str, permalink: str) -> None:
        super().__init__()
        self._channel = channel
        self._title = title[:55] or "(no title)"
        self._permalink = permalink

    def compose(self) -> ComposeResult:
        yield Static(f"#{self._channel}", classes="thread-channel")
        yield Static(self._title, classes="thread-title")
        if self._permalink:
            link_text = Text("open ↗", style=f"link {self._permalink}")
            yield Static(link_text, classes="thread-link")


class ThreadExplorer(Widget):
    """Side panel listing all threads explored in the current session."""

    DEFAULT_CSS = """
    ThreadExplorer {
        width: 36;
        background: $surface;
        border-left: tall $primary-darken-2;
        display: none;
        padding: 1;
        overflow-y: auto;
    }
    ThreadExplorer.visible {
        display: block;
    }
    """

    visible_panel: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        yield Static("Threads Explored", id="thread-panel-title")

    def add_thread(self, channel: str, title: str, permalink: str) -> None:
        self.mount(ThreadItem(channel=channel, title=title, permalink=permalink))

    def clear_threads(self) -> None:
        for item in self.query(ThreadItem):
            item.remove()

    def watch_visible_panel(self, value: bool) -> None:
        if value:
            self.add_class("visible")
        else:
            self.remove_class("visible")


# ------------------------------------------------------------------ #
# Stats bar                                                           #
# ------------------------------------------------------------------ #


class StatsBar(Widget):
    """Bottom bar showing token usage, elapsed time, tool calls."""

    DEFAULT_CSS = """
    StatsBar {
        height: 1;
        layout: horizontal;
        align: left middle;
        padding: 0 2;
        background: $surface-darken-1;
    }
    """

    tokens: reactive[int] = reactive(0)
    tool_calls: reactive[int] = reactive(0)
    threads: reactive[int] = reactive(0)
    elapsed: reactive[float] = reactive(0.0)
    model_name: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Static("", id="stat-tokens", classes="stat-item")
        yield Static("", id="stat-tools", classes="stat-item")
        yield Static("", id="stat-threads", classes="stat-item")
        yield Static("", id="stat-elapsed", classes="stat-item")
        yield Static("", id="stat-model", classes="stat-item")

    def _fmt(self) -> None:
        try:
            self.query_one("#stat-tokens", Static).update(
                f"tokens [bold cyan]{self.tokens}[/bold cyan]" if self.tokens else ""
            )
            self.query_one("#stat-tools", Static).update(
                f"tools [bold cyan]{self.tool_calls}[/bold cyan]" if self.tool_calls else ""
            )
            self.query_one("#stat-threads", Static).update(
                f"threads [bold cyan]{self.threads}[/bold cyan]" if self.threads else ""
            )
            self.query_one("#stat-elapsed", Static).update(f"[dim]{self.elapsed:.1f}s[/dim]" if self.elapsed else "")
            self.query_one("#stat-model", Static).update(f"[dim]{self.model_name}[/dim]" if self.model_name else "")
        except Exception:
            pass

    def watch_tokens(self, _: int) -> None:
        self._fmt()

    def watch_tool_calls(self, _: int) -> None:
        self._fmt()

    def watch_threads(self, _: int) -> None:
        self._fmt()

    def watch_elapsed(self, _: float) -> None:
        self._fmt()

    def watch_model_name(self, _: str) -> None:
        self._fmt()

    def update_stats(
        self,
        tokens: int = 0,
        tool_calls: int = 0,
        threads: int = 0,
        elapsed: float = 0.0,
    ) -> None:
        self.tokens = tokens
        self.tool_calls = tool_calls
        self.threads = threads
        self.elapsed = elapsed


# ------------------------------------------------------------------ #
# Welcome screen                                                      #
# ------------------------------------------------------------------ #


_WELCOME_LOGO = """\
╔╦╗┌─┐┌┬┐┌┬┐┌─┐┬─┐┌┬┐┬┌┐┌┌┬┐
║║║├─┤ │  │ ├┤ ├┬┘│││││││ ││
╩ ╩┴ ┴ ┴  ┴ └─┘┴└─┴ ┴┴┘└┘─┴┘"""


class WelcomeScreen(Widget):
    """Shown in the message area when no messages exist yet."""

    DEFAULT_CSS = """
    WelcomeScreen {
        width: 1fr;
        height: 1fr;
        align: center middle;
        layout: vertical;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = []  # type: ignore[assignment]

    def compose(self) -> ComposeResult:
        yield Static(_BANNER, id="welcome-logo", markup=False)
        yield Static(
            "Ask questions about your Mattermost workspace",
            id="welcome-tagline",
        )
        yield Static(
            "[dim]Enter[/dim] send · [dim]Ctrl+T[/dim] threads · [dim]Ctrl+L[/dim] clear · [dim]Ctrl+C[/dim] quit",
            id="welcome-hints",
            markup=True,
        )


# ------------------------------------------------------------------ #
# Thinking / streaming indicator                                      #
# ------------------------------------------------------------------ #


class ThinkingIndicator(Widget):
    """Animated indicator shown while the agent is working."""

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    DEFAULT_CSS = """
    ThinkingIndicator {
        height: 2;
        layout: horizontal;
        align: left middle;
        padding: 0 2;
        color: $primary;
        display: none;
    }
    ThinkingIndicator.active {
        display: block;
    }
    """

    _frame: reactive[int] = reactive(0)
    status_text: reactive[str] = reactive("Thinking…")

    def compose(self) -> ComposeResult:
        yield Static("", id="think-spinner")
        yield Static("", id="think-text")

    def on_mount(self) -> None:
        self.set_interval(0.08, self._tick)

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % len(self._FRAMES)
        try:
            self.query_one("#think-spinner", Static).update(f"[bold cyan]{self._FRAMES[self._frame]}[/bold cyan]  ")
            self.query_one("#think-text", Static).update(f"[dim]{markup_escape(self.status_text)}[/dim]")
        except Exception:
            pass

    def set_status(self, text: str) -> None:
        self.status_text = text

    def show(self) -> None:
        self.add_class("active")

    def hide(self) -> None:
        self.remove_class("active")


# ------------------------------------------------------------------ #
# Key bindings hint bar                                               #
# ------------------------------------------------------------------ #


class KeyBindingsBar(Widget):
    """One-line key bindings hint at the bottom of the screen."""

    DEFAULT_CSS = """
    KeyBindingsBar {
        height: 1;
        layout: horizontal;
        align: left middle;
        padding: 0 2;
        background: $surface-darken-2;
        color: $text-muted;
    }
    """

    _HINTS = [
        ("Enter", "send"),
        ("Ctrl+T", "threads"),
        ("Ctrl+L", "clear"),
        ("Ctrl+A", "activity"),
        ("Ctrl+C", "quit"),
    ]

    def compose(self) -> ComposeResult:
        parts: list[str] = []
        for key, label in self._HINTS:
            parts.append(f"[bold cyan]{key}[/bold cyan] [dim]{label}[/dim]")
        yield Static("  ".join(parts), markup=True)


# ------------------------------------------------------------------ #
# Message scroll container                                            #
# ------------------------------------------------------------------ #


class MessageList(ScrollableContainer):
    """Scrollable container that holds all MessageBubble widgets."""

    DEFAULT_CSS = """
    MessageList {
        height: 1fr;
        padding: 1 2;
        scrollbar-color: $primary-darken-2 $surface;
        scrollbar-size: 1 1;
    }
    """

    def scroll_to_bottom(self) -> None:
        self.scroll_end(animate=True, duration=0.3)
