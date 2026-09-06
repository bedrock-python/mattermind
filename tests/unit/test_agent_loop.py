from __future__ import annotations

import json
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mattermind.agent.loop import AgentLoop
from mattermind.agent.state import AgentState
from mattermind.agent.tools import execute_tool
from mattermind.config.models import AgentConfig, AppConfig, LLMConfig, MattermostConfig
from mattermind.mattermost.models import Post, SearchHit, Thread
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


# ------------------------------------------------------------------ #
# execute_tool — max_link_depth                                       #
# ------------------------------------------------------------------ #


def _thread(post_id: str = "post001", message: str = "hello", channel_id: str = "chan001") -> Thread:
    return Thread(
        root_post_id=post_id,
        posts=[
            Post(
                id=post_id,
                create_at=1_700_000_000_000,
                user_id="user001",
                channel_id=channel_id,
                message=message,
                root_id="",
            )
        ],
    )


async def _get_thread(
    post_id: str,
    state: AgentState,
    client: AsyncMock,
    config: AgentConfig | None = None,
) -> dict[str, Any]:
    result_str = await execute_tool(
        tool_name="mm_get_thread",
        tool_args={"post_id": post_id},
        client=client,
        team_id="team001",
        state=state,
        config=config or AgentConfig(),
        mm_url="https://mm.example.com",
        mm_team="engineering",
    )
    return cast(dict[str, Any], json.loads(result_str))


@pytest.mark.unit
@pytest.mark.asyncio
async def test__execute_tool__post_at_max_link_depth__thread_is_fetched(mm_client: AsyncMock) -> None:
    mm_client.get_thread = AsyncMock(return_value=_thread("post002"))
    state = AgentState()
    state.link_depth["post002"] = 2

    result = await _get_thread("post002", state, mm_client, AgentConfig(max_link_depth=2))

    assert result["root_post_id"] == "post002"


@pytest.mark.unit
@pytest.mark.asyncio
async def test__execute_tool__post_beyond_max_link_depth__returns_error_json(mm_client: AsyncMock) -> None:
    mm_client.get_thread = AsyncMock(return_value=_thread("post002"))
    state = AgentState()
    state.link_depth["post002"] = 3

    result = await _get_thread("post002", state, mm_client, AgentConfig(max_link_depth=2))

    assert "max_link_depth" in result["error"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test__execute_tool__post_beyond_max_link_depth__client_not_called(mm_client: AsyncMock) -> None:
    mm_client.get_thread = AsyncMock(return_value=_thread("post002"))
    state = AgentState()
    state.link_depth["post002"] = 3

    await _get_thread("post002", state, mm_client, AgentConfig(max_link_depth=2))

    mm_client.get_thread.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test__execute_tool__thread_links_to_another_post__linked_post_is_one_level_deeper(
    mm_client: AsyncMock,
) -> None:
    linked = "https://mm.example.com/engineering/pl/postaaa0002"
    mm_client.get_thread = AsyncMock(return_value=_thread("postaaa0001", message=f"see {linked}"))
    state = AgentState()

    await _get_thread("postaaa0001", state, mm_client)

    assert state.link_depth["postaaa0002"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test__execute_tool__link_chain_longer_than_max_depth__last_hop_is_refused(
    mm_client: AsyncMock,
) -> None:
    config = AgentConfig(max_link_depth=1)
    state = AgentState()
    mm_client.get_thread = AsyncMock(return_value=_thread("postaaa0001", message="see /pl/postaaa0002"))
    await _get_thread("postaaa0001", state, mm_client, config)
    mm_client.get_thread = AsyncMock(return_value=_thread("postaaa0002", message="see /pl/postaaa0003"))
    await _get_thread("postaaa0002", state, mm_client, config)

    mm_client.get_thread = AsyncMock(return_value=_thread("postaaa0003"))
    result = await _get_thread("postaaa0003", state, mm_client, config)

    assert "max_link_depth" in result["error"]


# ------------------------------------------------------------------ #
# execute_tool — explored threads                                     #
# ------------------------------------------------------------------ #


@pytest.mark.unit
@pytest.mark.asyncio
async def test__execute_tool__channel_name_known__explored_thread_uses_the_name(mm_client: AsyncMock) -> None:
    mm_client.get_thread = AsyncMock(return_value=_thread("post001", channel_id="chan001"))
    state = AgentState()
    state.channel_names["chan001"] = "general"

    await _get_thread("post001", state, mm_client)

    assert state.explored_threads[0]["channel"] == "general"


@pytest.mark.unit
@pytest.mark.asyncio
async def test__execute_tool__search_hits__record_channel_names_and_depth_zero(mm_client: AsyncMock) -> None:
    mm_client.search_posts = AsyncMock(
        return_value=[
            SearchHit(
                post_id="post001",
                message="incident",
                channel_id="chan001",
                channel_name="general",
                user_id="user001",
                username="jdoe",
                permalink="https://mm.example.com/engineering/pl/post001",
            )
        ]
    )
    state = AgentState()

    await execute_tool(
        tool_name="mm_search",
        tool_args={"query": "incident"},
        client=mm_client,
        team_id="team001",
        state=state,
        config=AgentConfig(),
        mm_url="https://mm.example.com",
        mm_team="engineering",
    )

    assert state.link_depth["post001"] == 0
    assert state.channel_names["chan001"] == "general"


@pytest.mark.unit
@pytest.mark.asyncio
async def test__agent_loop__thread_fetched__ask_result_carries_explored_threads(
    app_config: AppConfig, mm_client: AsyncMock, console: MagicMock
) -> None:
    mm_client.get_thread = AsyncMock(return_value=_thread("post001"))
    tool_call = _tool_call("mm_get_thread", {"post_id": "post001"})
    responses = [_llm_response(tool_calls=[tool_call]), _llm_response(content="Done.")]

    with patch("mattermind.agent.loop.AsyncOpenAI") as mock_openai:
        mock_openai.return_value.chat.completions.create = AsyncMock(side_effect=responses)
        loop = AgentLoop(config=app_config, client=mm_client, console=console)
        result = await loop.run("what happened?")

    assert result.explored_threads[0]["permalink"] == "https://mm.example.com/engineering/pl/post001"
