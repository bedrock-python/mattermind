"""Main agentic loop that drives tool calling and answer generation."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, cast

import httpx
import orjson
from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolMessageParam,
)
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from rich.console import Console

from mattermind.agent.prompts import SYSTEM_PROMPT
from mattermind.agent.state import AgentState
from mattermind.agent.tools import TOOL_DEFINITIONS, execute_tool
from mattermind.config.models import AppConfig
from mattermind.mattermost.client import MattermostClient
from mattermind.models import AskResult, TokenUsage

logger = logging.getLogger(__name__)


class AgentLoop:
    """Orchestrates the LLM + tool-calling loop to answer a user's question."""

    def __init__(
        self,
        config: AppConfig,
        client: MattermostClient,
        console: Console,
        verbose: bool = False,
    ) -> None:
        self._config = config
        self._mm_client = client
        self._console = console
        self._verbose = verbose

        self._llm = AsyncOpenAI(
            base_url=config.llm.base_url,
            api_key=config.llm.api_key,
            http_client=httpx.AsyncClient(
                verify=config.llm.verify_ssl,
                timeout=config.llm.request_timeout_seconds,
            ),
        )

    async def run(
        self,
        question: str,
        on_status: Callable[[str], None] | None = None,
    ) -> AskResult:
        """Run the agentic loop for a given question and return AskResult."""
        start = time.monotonic()

        state = AgentState()

        # Resolve team_id once
        if on_status:
            on_status("Connecting to Mattermost...")
        if not self._config.mattermost.team:
            raise ValueError("Mattermost team is not set. Add 'team' to your config or use --team.")
        team_id = await self._mm_client.get_team_id(self._config.mattermost.team)

        system = SYSTEM_PROMPT.format(max_depth=self._config.agent.max_link_depth)

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ]

        answer = ""
        iteration = 0

        while iteration < self._config.agent.max_iterations:
            iteration += 1

            if on_status:
                on_status(f"Thinking... (iteration {iteration})")

            logger.debug("LLM call iteration %d", iteration)

            typed_tools = cast(list[ChatCompletionToolParam], TOOL_DEFINITIONS)
            response = await self._llm.chat.completions.create(
                model=self._config.llm.model,
                messages=messages,
                tools=typed_tools,
                tool_choice="auto",
                temperature=self._config.llm.temperature,
                max_tokens=self._config.llm.max_tokens_per_response,
                timeout=self._config.llm.request_timeout_seconds,
            )

            # Track token usage
            if response.usage:
                state.token_usage = state.token_usage.add(
                    TokenUsage(
                        prompt_tokens=response.usage.prompt_tokens,
                        completion_tokens=response.usage.completion_tokens,
                        total_tokens=response.usage.total_tokens,
                    )
                )

            # Check budget
            if state.token_usage.total_tokens >= self._config.agent.total_token_budget:
                logger.warning("Token budget exhausted at iteration %d", iteration)
                if on_status:
                    on_status(f"Token budget exhausted ({state.token_usage.total_tokens:,} tokens). Continue? [y/N] ")
                confirmed = await asyncio.get_event_loop().run_in_executor(None, self._ask_continue)
                if confirmed:
                    # Double the remaining budget and keep going
                    self._config.agent.total_token_budget = (
                        state.token_usage.total_tokens + self._config.agent.total_token_budget
                    )
                    logger.debug("Budget extended to %d", self._config.agent.total_token_budget)
                    continue
                state.incomplete = True
                if on_status:
                    on_status("Stopped by user.")
                break

            choice = response.choices[0]
            message = choice.message

            # Append assistant message to conversation
            messages.append(cast(ChatCompletionMessageParam, message.model_dump(exclude_none=True)))

            # Only handle function tool calls (ignore custom tool calls).
            # Use isinstance to satisfy mypy; MagicMock objects in tests pass this check
            # because MagicMock supports arbitrary attribute access and isinstance checks.
            raw_tool_calls = message.tool_calls or []
            tool_calls: list[ChatCompletionMessageToolCall] = [
                tc  # type: ignore[misc]
                for tc in raw_tool_calls
                if hasattr(tc, "function") and hasattr(tc, "id")
            ]

            if not tool_calls:
                # LLM gave a final text answer (or only unsupported custom tools)
                answer = message.content or ""
                if on_status:
                    on_status("Answer ready.")
                break

            # --- Execute all tool calls (optionally in parallel) ---
            if on_status:
                tool_names = ", ".join(tc.function.name for tc in tool_calls)
                on_status(f"Calling tools: {tool_names}")

            if self._verbose:
                for tc in tool_calls:
                    self._console.print(f"[dim]Tool call: {tc.function.name}({tc.function.arguments})[/dim]")

            tool_tasks = [
                self._run_tool(tc.id, tc.function.name, tc.function.arguments, team_id, state) for tc in tool_calls
            ]

            if self._config.agent.parallel_tool_calls:
                tool_results = await asyncio.gather(*tool_tasks, return_exceptions=True)
            else:
                tool_results = []
                for task in tool_tasks:
                    tool_results.append(await task)

            # Append tool results to message history
            for tc, result in zip(tool_calls, tool_results, strict=False):
                result_str = (
                    orjson.dumps({"error": str(result)}).decode() if isinstance(result, BaseException) else str(result)
                )

                if self._verbose:
                    self._console.print(f"[dim]Tool result ({tc.function.name}): {result_str[:200]}[/dim]")

                tool_msg: ChatCompletionToolMessageParam = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                }
                messages.append(tool_msg)

        else:
            # Iteration limit reached without a final answer
            state.incomplete = True
            if on_status:
                on_status("Iteration limit reached — stopping early.")
            # Use the last assistant content if any
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    answer = str(msg.get("content") or "")
                    break

        elapsed = time.monotonic() - start

        # Collect unique permalinks from explored threads
        permalinks = list({t["permalink"] for t in state.explored_threads if t.get("permalink")})

        return AskResult(
            answer=answer,
            threads_explored=state.threads_fetched,
            tool_calls_made=state.tool_calls_made,
            token_usage=state.token_usage,
            elapsed_seconds=elapsed,
            incomplete=state.incomplete,
            permalinks=permalinks,
            explored_threads=state.explored_threads,
        )

    def _ask_continue(self) -> bool:
        """Prompt the user synchronously (runs in a thread executor)."""
        try:
            answer = input("Continue beyond token budget? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        else:
            return answer in ("y", "yes", "д", "да")

    async def _run_tool(
        self,
        _tool_call_id: str,
        tool_name: str,
        arguments_json: str,
        team_id: str,
        state: AgentState,
    ) -> str:
        """Parse arguments and delegate to execute_tool."""
        try:
            args: dict[str, Any] = orjson.loads(arguments_json)
        except orjson.JSONDecodeError as exc:
            return orjson.dumps({"error": f"Invalid tool arguments JSON: {exc}"}).decode()

        return await execute_tool(
            tool_name=tool_name,
            tool_args=args,
            client=self._mm_client,
            team_id=team_id,
            state=state,
            config=self._config.agent,
            mm_url=self._config.mattermost.url,
            mm_team=self._config.mattermost.team or "",
        )
