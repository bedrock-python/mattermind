"""Tool definitions and execution for the Mattermind agent."""

from __future__ import annotations

import logging
import re
from typing import Any

import orjson

from mattermind.agent.state import AgentState
from mattermind.config.models import AgentConfig
from mattermind.mattermost.client import MattermostClient

logger = logging.getLogger(__name__)


def _dumps(obj: Any) -> str:
    return orjson.dumps(obj).decode()


# ------------------------------------------------------------------ #
# OpenAI function-calling tool definitions                            #
# ------------------------------------------------------------------ #

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "mm_search",
            "description": (
                "Full-text search for posts in the Mattermost team. "
                "Returns a list of matching posts with channel names and post IDs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search terms. Supports Mattermost search syntax.",
                    },
                    "channel": {
                        "type": "string",
                        "description": "Optional: limit search to this channel name.",
                    },
                    "since": {
                        "type": "string",
                        "description": "Optional: ISO date string, e.g. '2024-01-01', to filter recent posts.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 20, max 60).",
                        "default": 20,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mm_get_thread",
            "description": (
                "Fetch the complete thread (root post + all replies) for the given post_id. "
                "Use this after mm_search to read the full context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "post_id": {
                        "type": "string",
                        "description": "The Mattermost post ID.",
                    },
                },
                "required": ["post_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mm_resolve_permalink",
            "description": (
                "Parse a Mattermost permalink URL and return the post_id embedded in it. "
                "Use this when you find a link like https://mm.company.com/team/pl/abc123 "
                "in a message and want to fetch that thread."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full Mattermost permalink URL.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mm_get_user",
            "description": "Look up a Mattermost user's display name and username by user ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The Mattermost user ID.",
                    },
                },
                "required": ["user_id"],
            },
        },
    },
]

# ------------------------------------------------------------------ #
# Permalink parsing helper                                            #
# ------------------------------------------------------------------ #

_PERMALINK_RE = re.compile(r"/pl/([A-Za-z0-9]{8,})")


def parse_post_id_from_permalink(url: str) -> str | None:
    """Extract the post ID from a Mattermost permalink URL.

    Returns the post_id string, or None if the URL is not a valid permalink.
    """
    match = _PERMALINK_RE.search(url)
    if match:
        return match.group(1)
    return None


# ------------------------------------------------------------------ #
# Tool execution dispatcher                                           #
# ------------------------------------------------------------------ #


async def execute_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    client: MattermostClient,
    team_id: str,
    state: AgentState,
    config: AgentConfig,
    mm_url: str,
    mm_team: str,
) -> str:
    """Dispatch a tool call and return a JSON string result.

    All errors are caught and returned as JSON error objects so the LLM
    can decide how to proceed rather than crashing the loop.
    """
    state.tool_calls_made += 1

    try:
        if tool_name == "mm_search":
            return await _tool_search(tool_args, client, team_id, state)
        if tool_name == "mm_get_thread":
            return await _tool_get_thread(tool_args, client, state, config, mm_url, mm_team)
        if tool_name == "mm_resolve_permalink":
            return _tool_resolve_permalink(tool_args)
        if tool_name == "mm_get_user":
            return await _tool_get_user(tool_args, client)
    except Exception as exc:
        logger.warning("Tool %s raised: %s", tool_name, exc)
        return _dumps({"error": str(exc)})

    return _dumps({"error": f"Unknown tool: {tool_name}"})


async def _tool_search(
    args: dict[str, Any],
    client: MattermostClient,
    team_id: str,
    state: AgentState,
) -> str:
    query: str = args["query"]
    # channel filter is passed through to the search call
    channel_name: str | None = args.get("channel")
    limit: int = min(int(args.get("limit", 20)), 60)

    # Build search query with optional date filter and channel filter
    since: str | None = args.get("since")
    full_query = query
    if since:
        full_query = f"{full_query} after:{since}"
    if channel_name:
        full_query = f"{full_query} in:{channel_name}"

    hits = await client.search_posts(team_id=team_id, query=full_query, channel_id=None, per_page=limit)

    for hit in hits:
        # A search hit is the start of a link chain, not a link away from one.
        state.link_depth.setdefault(hit.post_id, 0)
        if hit.channel_id:
            state.channel_names.setdefault(hit.channel_id, hit.channel_name)

    results = [
        {
            "post_id": h.post_id,
            "message": h.message[:500],  # truncate for context efficiency
            "channel_name": h.channel_name,
            "user_id": h.user_id,
            "username": h.username,
            "permalink": h.permalink,
        }
        for h in hits
    ]
    return _dumps({"results": results, "count": len(results)})


async def _tool_get_thread(
    args: dict[str, Any],
    client: MattermostClient,
    state: AgentState,
    config: AgentConfig,
    mm_url: str,
    mm_team: str,
) -> str:
    post_id: str = args["post_id"]

    if post_id in state.visited_post_ids:
        return _dumps({"error": f"Thread for post {post_id} already fetched — skipping to avoid duplication."})

    if state.threads_fetched >= config.max_threads_per_query:
        state.incomplete = True
        return _dumps({"error": "Thread fetch limit reached. Stopping exploration."})

    # Depth 0 is a search hit; every permalink found inside a thread is one level
    # deeper. Posts we have never seen a link to are treated as a fresh start.
    depth = state.link_depth.setdefault(post_id, 0)
    if depth > config.max_link_depth:
        return _dumps(
            {
                "error": (
                    f"Post {post_id} is {depth} links away from a search hit, "
                    f"beyond max_link_depth={config.max_link_depth}. Do not follow this link."
                )
            }
        )

    state.visited_post_ids.add(post_id)

    thread = await client.get_thread(post_id)
    state.threads_fetched += 1

    channel_id = thread.posts[0].channel_id if thread.posts else ""

    # Track for the summary
    first_msg = thread.posts[0].message[:80] if thread.posts else ""
    root_permalink = f"{mm_url.rstrip('/')}/{mm_team}/pl/{thread.root_post_id}"

    state.explored_threads.append(
        {
            "post_id": thread.root_post_id,
            "channel": state.channel_names.get(channel_id, channel_id),
            "title": first_msg,
            "permalink": root_permalink,
        }
    )

    # Serialise posts — include permalink for each so LLM can cite
    serialised_posts = []
    for post in thread.posts:
        permalink = f"{mm_url.rstrip('/')}/{mm_team}/pl/{post.id}"
        # Everything this thread links to sits one level deeper.
        for linked_id in _PERMALINK_RE.findall(post.message):
            state.link_depth.setdefault(linked_id, depth + 1)
        serialised_posts.append(
            {
                "post_id": post.id,
                "user_id": post.user_id,
                "message": post.message,
                "created_at": post.created_at.isoformat(),
                "permalink": permalink,
            }
        )

    return _dumps(
        {
            "root_post_id": thread.root_post_id,
            "post_count": len(thread.posts),
            "posts": serialised_posts,
        }
    )


def _tool_resolve_permalink(args: dict[str, Any]) -> str:
    url: str = args["url"]
    post_id = parse_post_id_from_permalink(url)
    if post_id is None:
        return _dumps(
            {"error": f"Could not extract post_id from URL: {url!r}. Expected format: https://host/team/pl/POST_ID"}
        )
    return _dumps({"post_id": post_id})


async def _tool_get_user(
    args: dict[str, Any],
    client: MattermostClient,
) -> str:
    user_id: str = args["user_id"]
    user = await client.get_user(user_id)
    return _dumps(
        {
            "user_id": user.id,
            "username": user.username,
            "display_name": user.display_name,
        }
    )
