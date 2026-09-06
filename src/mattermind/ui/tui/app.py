"""Mattermind TUI — main Textual application."""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import ClassVar

from rich.console import Console as RichConsole
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Input, Static

from mattermind.agent.loop import AgentLoop
from mattermind.config.loader import load_config
from mattermind.config.models import AppConfig
from mattermind.mattermost.client import MattermostClient
from mattermind.models import AskResult, TokenUsage

from .widgets import (
    AgentActivityLog,
    KeyBindingsBar,
    MessageBubble,
    MessageList,
    StatsBar,
    ThinkingIndicator,
    ThreadExplorer,
    WelcomeScreen,
)

# CSS path relative to this file
_CSS_PATH = Path(__file__).parent / "theme.tcss"

# ------------------------------------------------------------------ #
# App                                                                  #
# ------------------------------------------------------------------ #


class MattermindApp(App[None]):
    """Interactive TUI chat interface for Mattermind."""

    CSS_PATH = str(_CSS_PATH)

    TITLE = "Mattermind"
    SUB_TITLE = "Mattermost AI assistant"

    BINDINGS: ClassVar[list[Binding]] = [  # type: ignore[assignment]
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("ctrl+l", "clear_chat", "Clear chat", show=False),
        Binding("ctrl+t", "toggle_threads", "Threads", show=False),
        Binding("ctrl+a", "toggle_activity", "Activity log", show=False),
        Binding("escape", "cancel_query", "Cancel", show=False),
    ]

    def __init__(
        self,
        config: AppConfig,
        config_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._config_path = config_path
        self._busy = False
        self._current_worker: asyncio.Task[None] | None = None
        self._session_result = AskResult(
            answer="",
            threads_explored=0,
            tool_calls_made=0,
            token_usage=TokenUsage(),
            elapsed_seconds=0.0,
        )
        self._all_threads: list[dict[str, str]] = []
        self._show_activity = True

    # ---------------------------------------------------------------- #
    # Compose                                                            #
    # ---------------------------------------------------------------- #

    def compose(self) -> ComposeResult:
        # ── Header ──────────────────────────────────────────────────
        with Horizontal(id="header"):
            yield Static("⬡  MATTERMIND", id="header-logo")
            yield Static(self._config.llm.model, id="header-model")
            yield Static("● connected", id="header-status")

        # ── Body ─────────────────────────────────────────────────────
        with Horizontal(id="main-container"):
            # Left: chat + input + activity
            with Vertical(id="chat-area"):
                yield WelcomeScreen(id="welcome")
                yield MessageList(id="messages-scroll")
                yield ThinkingIndicator(id="thinking")
                yield AgentActivityLog()
                with Horizontal(id="input-bar"):
                    yield Input(
                        placeholder="Ask anything about your Mattermost…",
                        id="chat-input",
                    )
                    yield Static("Send  ↵", id="send-btn", markup=False)

            # Right: thread explorer (hidden by default)
            yield ThreadExplorer(id="thread-panel")

        # ── Bottom bars ───────────────────────────────────────────────
        yield StatsBar(id="stats-bar")
        yield KeyBindingsBar()

    # ---------------------------------------------------------------- #
    # Mount / startup                                                    #
    # ---------------------------------------------------------------- #

    def on_mount(self) -> None:
        stats = self.query_one(StatsBar)
        stats.model_name = self._config.llm.model

        # Hide messages container until first message
        self.query_one("#messages-scroll", MessageList).display = False

        # Focus input
        self.query_one("#chat-input", Input).focus()

    # ---------------------------------------------------------------- #
    # Input handling                                                     #
    # ---------------------------------------------------------------- #

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """User pressed Enter in the chat input."""
        self._send_message(event.value.strip())

    def on_static_click(self, event: Static.Clicked) -> None:  # type: ignore[name-defined]
        """User clicked the Send button."""
        if event.widget.id == "send-btn":
            inp = self.query_one("#chat-input", Input)
            self._send_message(inp.value.strip())

    def _send_message(self, text: str) -> None:
        if not text or self._busy:
            return

        inp = self.query_one("#chat-input", Input)
        inp.value = ""

        # Show messages container and hide welcome
        self._show_messages_area()

        # Add user bubble
        self._add_bubble("user", text)

        # Run agent
        self._run_agent(text)

    # ---------------------------------------------------------------- #
    # Layout helpers                                                     #
    # ---------------------------------------------------------------- #

    def _show_messages_area(self) -> None:
        try:
            self.query_one("#welcome").display = False
        except NoMatches:
            pass
        self.query_one("#messages-scroll", MessageList).display = True

    def _add_bubble(self, role: str, content: str, msg_id: str | None = None) -> MessageBubble:
        msg_id = msg_id or f"msg-{uuid.uuid4().hex[:8]}"
        bubble = MessageBubble(role=role, content=content, message_id=msg_id)
        messages = self.query_one("#messages-scroll", MessageList)
        messages.mount(bubble)
        messages.scroll_to_bottom()
        return bubble

    def _get_activity_log(self) -> AgentActivityLog:
        return self.query_one(AgentActivityLog)

    def _get_thinking(self) -> ThinkingIndicator:
        return self.query_one("#thinking", ThinkingIndicator)

    def _get_stats(self) -> StatsBar:
        return self.query_one(StatsBar)

    # ---------------------------------------------------------------- #
    # Agent worker                                                       #
    # ---------------------------------------------------------------- #

    @work(exclusive=True, thread=False)
    async def _run_agent(self, question: str) -> None:  # type: ignore[override]
        """Run the agent loop in the background and stream status updates."""
        self._busy = True
        inp = self.query_one("#chat-input", Input)
        inp.disabled = True

        thinking = self._get_thinking()
        thinking.show()
        activity = self._get_activity_log()

        # Placeholder assistant bubble for streaming status
        assistant_bubble_id = f"msg-{uuid.uuid4().hex[:8]}"
        assistant_bubble = self._add_bubble("assistant", "_Thinking…_", msg_id=assistant_bubble_id)

        start = time.monotonic()

        def on_status(msg: str) -> None:
            """Called by agent loop on each status change."""
            thinking.set_status(msg)
            kind = "tool" if "tool" in msg.lower() or "call" in msg.lower() else "info"
            if "answer ready" in msg.lower() or "done" in msg.lower():
                kind = "done"
            if "error" in msg.lower() or "exhaust" in msg.lower():
                kind = "error"
            activity.add_line(msg, kind=kind)
            assistant_bubble.update_content(f"_{msg}_")

        try:
            async with MattermostClient(self._config.mattermost) as mm_client:
                loop = AgentLoop(
                    config=self._config,
                    client=mm_client,
                    console=RichConsole(quiet=True),
                    verbose=False,
                )
                result: AskResult = await loop.run(question, on_status=on_status)

            # Update bubble with real answer
            assistant_bubble.update_content(result.answer or "_No answer returned._")

            # Update thread explorer
            if result.permalinks:
                explorer = self.query_one(ThreadExplorer)
                for link in result.permalinks:
                    explorer.add_thread(
                        channel="mattermost",
                        title=link,
                        permalink=link,
                    )

            # Accumulate session stats
            self._session_result = AskResult(
                answer=result.answer,
                threads_explored=self._session_result.threads_explored + result.threads_explored,
                tool_calls_made=self._session_result.tool_calls_made + result.tool_calls_made,
                token_usage=self._session_result.token_usage.add(result.token_usage),
                elapsed_seconds=time.monotonic() - start,
                incomplete=result.incomplete,
                permalinks=self._session_result.permalinks + result.permalinks,
            )

            stats = self._get_stats()
            stats.update_stats(
                tokens=self._session_result.token_usage.total_tokens,
                tool_calls=self._session_result.tool_calls_made,
                threads=self._session_result.threads_explored,
                elapsed=time.monotonic() - start,
            )

            if result.incomplete:
                activity.add_line("⚠ Stopped early (budget/limit reached)", kind="error")

        except asyncio.CancelledError:
            assistant_bubble.update_content("_Query cancelled._")
            activity.add_line("Cancelled", kind="error")
        except Exception as exc:
            assistant_bubble.update_content(f"**Error:** {exc}")
            activity.add_line(f"Error: {exc}", kind="error")
        finally:
            thinking.hide()
            inp.disabled = False
            inp.focus()
            self._busy = False
            self.query_one("#messages-scroll", MessageList).scroll_to_bottom()

    # ---------------------------------------------------------------- #
    # Actions                                                            #
    # ---------------------------------------------------------------- #

    async def action_quit(self) -> None:
        self.exit()

    def action_clear_chat(self) -> None:
        """Remove all messages and reset to welcome screen."""
        messages = self.query_one("#messages-scroll", MessageList)
        for bubble in messages.query(MessageBubble):
            bubble.remove()
        messages.display = False
        try:
            self.query_one("#welcome").display = True
        except NoMatches:
            pass
        self.query_one(ThreadExplorer).clear_threads()
        self.query_one(AgentActivityLog).query(".activity-line").remove()
        self.query_one("#chat-input", Input).focus()

    def action_toggle_threads(self) -> None:
        explorer = self.query_one(ThreadExplorer)
        explorer.visible_panel = not explorer.visible_panel

    def action_toggle_activity(self) -> None:
        log = self.query_one(AgentActivityLog)
        self._show_activity = not self._show_activity
        log.display = self._show_activity

    def action_cancel_query(self) -> None:
        """Cancel the currently running agent query."""
        if self._busy:
            # Textual workers are cancelled via app.workers
            for worker in self.workers:
                if not worker.is_done:  # type: ignore[attr-defined]
                    worker.cancel()


# ------------------------------------------------------------------ #
# Entry point helper                                                   #
# ------------------------------------------------------------------ #


def run_tui(config_path: Path | None = None) -> None:
    """Load config and launch the TUI. Called from the CLI 'chat' command.

    Raises:
        ConfigError: the configuration is missing or invalid. The caller decides
            how to report it — the CLI renders a panel and exits 1.
    """
    config = load_config(config_path=config_path)

    app = MattermindApp(config=config, config_path=config_path)
    app.run()
