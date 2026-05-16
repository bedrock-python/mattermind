"""Integration tests — require a real Mattermost server and LLM endpoint.

Run with:
    uv run pytest -m integration
"""

from __future__ import annotations

import os

import pytest
from rich.console import Console

from mattermind.agent.loop import AgentLoop
from mattermind.config.loader import load_config
from mattermind.mattermost.client import MattermostClient
from mattermind.models import AskResult


@pytest.fixture(scope="module")
def config() -> object:
    return load_config()


@pytest.fixture(scope="module")
def question() -> str:
    return os.environ.get("MATTERMIND_TEST_QUESTION", "What is the latest deployment status?")


# ------------------------------------------------------------------ #
# Mattermost connection                                               #
# ------------------------------------------------------------------ #


@pytest.mark.integration
@pytest.mark.asyncio
async def test__mattermost_client__valid_credentials__connection_succeeds(config) -> None:  # type: ignore[no-untyped-def]
    async with MattermostClient(config.mattermost) as client:
        result = await client.validate_connection()

    assert result is True, "Could not connect to Mattermost. Check MM_TOKEN and MM_URL."


# ------------------------------------------------------------------ #
# Search                                                              #
# ------------------------------------------------------------------ #


@pytest.mark.integration
@pytest.mark.asyncio
async def test__search_posts__common_term__returns_list(config) -> None:  # type: ignore[no-untyped-def]
    async with MattermostClient(config.mattermost) as client:
        team_id = await client.get_team_id(config.mattermost.team)
        hits = await client.search_posts(team_id, "the", per_page=5)

    assert isinstance(hits, list)


# ------------------------------------------------------------------ #
# Full ask flow                                                       #
# ------------------------------------------------------------------ #


@pytest.mark.integration
@pytest.mark.asyncio
async def test__agent_loop__real_question__returns_ask_result(config, question) -> None:  # type: ignore[no-untyped-def]
    console = Console(quiet=True)

    async with MattermostClient(config.mattermost) as mm_client:
        loop = AgentLoop(config=config, client=mm_client, console=console)
        result = await loop.run(question)

    assert isinstance(result, AskResult)


@pytest.mark.integration
@pytest.mark.asyncio
async def test__agent_loop__real_question__answer_is_non_empty(config, question) -> None:  # type: ignore[no-untyped-def]
    console = Console(quiet=True)

    async with MattermostClient(config.mattermost) as mm_client:
        loop = AgentLoop(config=config, client=mm_client, console=console)
        result = await loop.run(question)

    assert result.answer


@pytest.mark.integration
@pytest.mark.asyncio
async def test__agent_loop__real_question__elapsed_time_positive(config, question) -> None:  # type: ignore[no-untyped-def]
    console = Console(quiet=True)

    async with MattermostClient(config.mattermost) as mm_client:
        loop = AgentLoop(config=config, client=mm_client, console=console)
        result = await loop.run(question)

    assert result.elapsed_seconds > 0
