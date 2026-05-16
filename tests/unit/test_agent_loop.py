from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mattermind.agent.loop import AgentLoop
from mattermind.agent.state import AgentState
from mattermind.agent.tools import execute_tool
from mattermind.config.models import AgentConfig, AppConfig, LLMConfig, MattermostConfig
from mattermind.models import AskResult


@pytest.fixture()
def app_config() -> AppConfig:
    return AppConfig(
        mattermost=MattermostConfig(
            url="https://mm.example.com",
            token="test-token",  # noqa: S106
            team="engineering",
        ),
        llm=LLMConfig(
            api_key="sk-test",
            model="gpt-4o-mini",
        ),
        agent=AgentConfig(
            max_iterations=10,
            total_token_budget=200_000,
            parallel_tool_calls=False,
        ),
    )


@pytest.fixture()
def tight_budget_config(app_config: AppConfig) -> AppConfig:
    return app_config.model_copy(update={"agent": app_config.agent.model_copy(update={"total_token_budget": 100})})


@pytest.fixture()
def two_iteration_config(app_config: AppConfig) -> AppConfig:
    return app_config.model_copy(update={"agent": app_config.agent.model_copy(update={"max_iterations": 2})})


@pytest.fixture()
def mm_client() -> AsyncMock:
    client = AsyncMock()
    client.get_team_id = AsyncMock(return_value="team001")
    return client


@pytest.fixture()
def console() -> MagicMock:
    c = MagicMock()
    c.print = MagicMock()
    return c


def _llm_response(
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    usage_prompt: int = 100,
    usage_completion: int = 50,
) -> MagicMock:
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls or []
    message.model_dump.return_value = {
        "role": "assistant",
        "content": content,
        "tool_calls": [],
    }

    choice = MagicMock()
    choice.message = message

    usage = MagicMock()
    usage.prompt_tokens = usage_prompt
    usage.completion_tokens = usage_completion
    usage.total_tokens = usage_prompt + usage_completion

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


def _tool_call(name: str, args: dict[str, Any], call_id: str = "call_001") -> MagicMock:
    func = MagicMock()
    func.name = name
    func.arguments = json.dumps(args)

    tc = MagicMock()
    tc.id = call_id
    tc.function = func
    return tc


# ------------------------------------------------------------------ #
# AgentLoop.run                                                       #
# ------------------------------------------------------------------ #


@pytest.mark.unit
@pytest.mark.asyncio
async def test__agent_loop__no_tool_calls__returns_ask_result(
    app_config: AppConfig, mm_client: AsyncMock, console: MagicMock
) -> None:
    response = _llm_response(content="The answer is 42.")

    with patch("mattermind.agent.loop.AsyncOpenAI") as MockOpenAI:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(return_value=response)
        MockOpenAI.return_value = mock_llm

        loop = AgentLoop(config=app_config, client=mm_client, console=console)
        result = await loop.run("What is the answer?")

    assert isinstance(result, AskResult)


@pytest.mark.unit
@pytest.mark.asyncio
async def test__agent_loop__no_tool_calls__answer_matches_llm_content(
    app_config: AppConfig, mm_client: AsyncMock, console: MagicMock
) -> None:
    response = _llm_response(content="The answer is 42.")

    with patch("mattermind.agent.loop.AsyncOpenAI") as MockOpenAI:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(return_value=response)
        MockOpenAI.return_value = mock_llm

        loop = AgentLoop(config=app_config, client=mm_client, console=console)
        result = await loop.run("What is the answer?")

    assert result.answer == "The answer is 42."


@pytest.mark.unit
@pytest.mark.asyncio
async def test__agent_loop__no_tool_calls__tool_calls_made_is_zero(
    app_config: AppConfig, mm_client: AsyncMock, console: MagicMock
) -> None:
    response = _llm_response(content="The answer is 42.")

    with patch("mattermind.agent.loop.AsyncOpenAI") as MockOpenAI:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(return_value=response)
        MockOpenAI.return_value = mock_llm

        loop = AgentLoop(config=app_config, client=mm_client, console=console)
        result = await loop.run("What is the answer?")

    assert result.tool_calls_made == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test__agent_loop__no_tool_calls__incomplete_is_false(
    app_config: AppConfig, mm_client: AsyncMock, console: MagicMock
) -> None:
    response = _llm_response(content="The answer is 42.")

    with patch("mattermind.agent.loop.AsyncOpenAI") as MockOpenAI:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(return_value=response)
        MockOpenAI.return_value = mock_llm

        loop = AgentLoop(config=app_config, client=mm_client, console=console)
        result = await loop.run("What is the answer?")

    assert result.incomplete is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test__agent_loop__one_tool_call_then_answer__answer_matches(
    app_config: AppConfig, mm_client: AsyncMock, console: MagicMock
) -> None:
    search_tc = _tool_call("mm_search", {"query": "incident database"}, call_id="call_search")
    first_response = _llm_response(tool_calls=[search_tc])
    second_response = _llm_response(content="Found incident in #general channel.")
    search_result = json.dumps(
        {"results": [{"post_id": "p001", "message": "DB is down", "channel_name": "general"}], "count": 1}
    )

    with patch("mattermind.agent.loop.AsyncOpenAI") as MockOpenAI:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(side_effect=[first_response, second_response])
        MockOpenAI.return_value = mock_llm

        with patch("mattermind.agent.tools.execute_tool", AsyncMock(return_value=search_result)):
            loop = AgentLoop(config=app_config, client=mm_client, console=console)
            result = await loop.run("What happened to the database?")

    assert result.answer == "Found incident in #general channel."


@pytest.mark.unit
@pytest.mark.asyncio
async def test__agent_loop__one_tool_call_then_answer__tool_calls_made_is_one(
    app_config: AppConfig, mm_client: AsyncMock, console: MagicMock
) -> None:
    search_tc = _tool_call("mm_search", {"query": "incident database"}, call_id="call_search")
    first_response = _llm_response(tool_calls=[search_tc])
    second_response = _llm_response(content="Found incident in #general channel.")
    search_result = json.dumps({"results": [], "count": 0})

    with patch("mattermind.agent.loop.AsyncOpenAI") as MockOpenAI:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(side_effect=[first_response, second_response])
        MockOpenAI.return_value = mock_llm

        with patch("mattermind.agent.tools.execute_tool", AsyncMock(return_value=search_result)):
            loop = AgentLoop(config=app_config, client=mm_client, console=console)
            result = await loop.run("What happened?")

    assert result.tool_calls_made == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test__agent_loop__max_iterations_reached__incomplete_is_true(
    two_iteration_config: AppConfig, mm_client: AsyncMock, console: MagicMock
) -> None:
    tc = _tool_call("mm_search", {"query": "test"}, "call_001")
    endless_response = _llm_response(tool_calls=[tc])
    search_result = json.dumps({"results": [], "count": 0})

    with patch("mattermind.agent.loop.AsyncOpenAI") as MockOpenAI:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(return_value=endless_response)
        MockOpenAI.return_value = mock_llm

        with patch("mattermind.agent.tools.execute_tool", AsyncMock(return_value=search_result)):
            loop = AgentLoop(config=two_iteration_config, client=mm_client, console=console)
            result = await loop.run("What is going on?")

    assert result.incomplete is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test__agent_loop__token_budget_exceeded__incomplete_is_true(
    tight_budget_config: AppConfig, mm_client: AsyncMock, console: MagicMock
) -> None:
    tc = _tool_call("mm_search", {"query": "test"}, "call_001")
    expensive_response = _llm_response(tool_calls=[tc], usage_prompt=150, usage_completion=100)
    final_response = _llm_response(content="Some answer.")
    search_result = json.dumps({"results": [], "count": 0})

    with patch("mattermind.agent.loop.AsyncOpenAI") as MockOpenAI:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(side_effect=[expensive_response, final_response])
        MockOpenAI.return_value = mock_llm

        with (
            patch("mattermind.agent.tools.execute_tool", AsyncMock(return_value=search_result)),
            patch("mattermind.agent.loop.AgentLoop._ask_continue", return_value=False),
        ):
            loop = AgentLoop(config=tight_budget_config, client=mm_client, console=console)
            result = await loop.run("What is happening?")

    assert result.incomplete is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test__agent_loop__tool_called__tool_result_passed_as_tool_message(
    app_config: AppConfig, mm_client: AsyncMock, console: MagicMock
) -> None:
    tc = _tool_call("mm_search", {"query": "test"}, "call_search")
    first_response = _llm_response(tool_calls=[tc])
    final_response = _llm_response(content="Done.")
    search_result = json.dumps({"results": [{"post_id": "p1", "message": "hi"}], "count": 1})

    captured_messages: list[list[Any]] = []

    async def capture_create(**kwargs: Any) -> Any:
        captured_messages.append(list(kwargs.get("messages", [])))
        if len(captured_messages) == 1:
            return first_response
        return final_response

    with patch("mattermind.agent.loop.AsyncOpenAI") as MockOpenAI:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(side_effect=capture_create)
        MockOpenAI.return_value = mock_llm

        with patch("mattermind.agent.tools.execute_tool", AsyncMock(return_value=search_result)):
            loop = AgentLoop(config=app_config, client=mm_client, console=console)
            await loop.run("Test question")

    second_call_roles = [
        m.get("role") if isinstance(m, dict) else getattr(m, "role", None) for m in captured_messages[1]
    ]
    assert "tool" in second_call_roles


# ------------------------------------------------------------------ #
# execute_tool                                                        #
# ------------------------------------------------------------------ #


@pytest.mark.unit
@pytest.mark.asyncio
async def test__execute_tool__already_visited_post__returns_error_json(mm_client: AsyncMock) -> None:
    state = AgentState()
    state.visited_post_ids.add("post001")
    config = AgentConfig()

    result_str = await execute_tool(
        tool_name="mm_get_thread",
        tool_args={"post_id": "post001"},
        client=mm_client,
        team_id="team001",
        state=state,
        config=config,
        mm_url="https://mm.example.com",
        mm_team="engineering",
    )

    result = json.loads(result_str)
    assert "error" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test__execute_tool__already_visited_post__error_mentions_already_fetched(
    mm_client: AsyncMock,
) -> None:
    state = AgentState()
    state.visited_post_ids.add("post001")
    config = AgentConfig()

    result_str = await execute_tool(
        tool_name="mm_get_thread",
        tool_args={"post_id": "post001"},
        client=mm_client,
        team_id="team001",
        state=state,
        config=config,
        mm_url="https://mm.example.com",
        mm_team="engineering",
    )

    result = json.loads(result_str)
    assert "already fetched" in result["error"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test__execute_tool__already_visited_post__client_not_called(mm_client: AsyncMock) -> None:
    state = AgentState()
    state.visited_post_ids.add("post001")
    config = AgentConfig()

    await execute_tool(
        tool_name="mm_get_thread",
        tool_args={"post_id": "post001"},
        client=mm_client,
        team_id="team001",
        state=state,
        config=config,
        mm_url="https://mm.example.com",
        mm_team="engineering",
    )

    mm_client.get_thread.assert_not_called()
