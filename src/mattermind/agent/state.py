"""Mutable agent state shared across the agentic loop iterations."""

from __future__ import annotations

from dataclasses import dataclass, field

from mattermind.models import TokenUsage


@dataclass
class AgentState:
    """Tracks all mutable state during an agent run."""

    visited_post_ids: set[str] = field(default_factory=set)
    """Post IDs of threads we have already fetched — prevents re-fetching."""

    link_depth: dict[str, int] = field(default_factory=dict)
    """Maps post_id -> depth at which it was discovered (0 = direct search hit)."""

    channel_names: dict[str, str] = field(default_factory=dict)
    """Maps channel_id -> channel name, as learned from search results."""

    token_usage: TokenUsage = field(default_factory=TokenUsage)
    """Cumulative token usage across all LLM calls."""

    threads_fetched: int = 0
    """How many mm_get_thread calls succeeded."""

    tool_calls_made: int = 0
    """Total number of tool calls dispatched."""

    explored_threads: list[dict[str, str]] = field(default_factory=list)
    """Metadata for the "Threads explored" section. Each entry:
    {"post_id": ..., "channel": ..., "title": ..., "permalink": ...}
    """

    incomplete: bool = False
    """True if the run was terminated early (budget / iteration limit)."""
