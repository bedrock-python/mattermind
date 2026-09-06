from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
import yaml
from typer.testing import CliRunner

from mattermind.cli import app as cli_app
from mattermind.cli.context import AppContext
from mattermind.models import AskResult, TokenUsage

runner = CliRunner()


@pytest.fixture(autouse=True)
def fresh_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every invocation a clean shared context."""
    monkeypatch.setattr(cli_app, "_ctx", AppContext())


@pytest.fixture(autouse=True)
def restore_root_logging() -> Iterator[None]:
    """The CLI calls logging.basicConfig(force=True); undo it afterwards."""
    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def _config_data(**sections: dict[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "mattermost": {
            "url": "https://mm.example.com",
            "token": "test-token-12345",
            "team": "engineering",
        },
        "llm": {
            "base_url": "https://llm.example.com/v1",
            "api_key": "sk-test-12345",
            "model": "gpt-4o-mini",
        },
    }
    data.update(sections)
    return data


@pytest.fixture()
def config_file(tmp_path: Path) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(_config_data()), encoding="utf-8")
    return p


@pytest.fixture()
def ask_result() -> AskResult:
    return AskResult(
        answer="The answer is 42.",
        threads_explored=1,
        tool_calls_made=2,
        token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        elapsed_seconds=1.5,
        explored_threads=[
            {
                "post_id": "post001",
                "channel": "general",
                "title": "auth migration",
                "permalink": "https://mm.example.com/engineering/pl/post001",
            }
        ],
    )


@pytest.fixture()
def stub_ask(monkeypatch: pytest.MonkeyPatch, ask_result: AskResult) -> None:
    """Replace the agent run with a canned result."""

    async def _fake_run_ask(*_args: object, **_kwargs: object) -> AskResult:
        return ask_result

    monkeypatch.setattr(cli_app, "_run_ask", _fake_run_ask)


# ------------------------------------------------------------------ #
# Global flags after the subcommand                                   #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__ask__json_flag_after_subcommand__exit_code_is_zero(config_file: Path, stub_ask: None) -> None:
    result = runner.invoke(cli_app.app, ["ask", "what shipped?", "--config", str(config_file), "--json"])

    assert result.exit_code == 0


@pytest.mark.unit
def test__ask__json_flag_after_subcommand__prints_json(config_file: Path, stub_ask: None) -> None:
    result = runner.invoke(cli_app.app, ["ask", "what shipped?", "--config", str(config_file), "--json"])

    assert '"answer": "The answer is 42."' in result.output


@pytest.mark.unit
def test__ask__json_flag_before_subcommand__prints_json(config_file: Path, stub_ask: None) -> None:
    result = runner.invoke(cli_app.app, ["--json", "--config", str(config_file), "ask", "what shipped?"])

    assert '"answer": "The answer is 42."' in result.output


@pytest.mark.unit
def test__config_show__config_flag_after_subcommand__reads_that_file(config_file: Path) -> None:
    result = runner.invoke(cli_app.app, ["config", "show", "--config", str(config_file), "--json"])

    assert str(config_file) in result.output


@pytest.mark.unit
def test__version__quiet_flag_before_subcommand__prints_the_version(config_file: Path) -> None:
    result = runner.invoke(cli_app.app, ["--quiet", "version"])

    assert "mattermind" in result.output


# ------------------------------------------------------------------ #
# --quiet                                                             #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__ask__quiet__prints_the_answer(config_file: Path, stub_ask: None) -> None:
    result = runner.invoke(cli_app.app, ["--quiet", "--config", str(config_file), "ask", "what shipped?"])

    assert "The answer is 42." in result.output


@pytest.mark.unit
def test__ask__quiet__omits_the_run_summary(config_file: Path, stub_ask: None) -> None:
    result = runner.invoke(cli_app.app, ["--quiet", "--config", str(config_file), "ask", "what shipped?"])

    assert "Run summary" not in result.output


@pytest.mark.unit
def test__ask__quiet__omits_the_banner(config_file: Path, stub_ask: None) -> None:
    result = runner.invoke(cli_app.app, ["--quiet", "--config", str(config_file), "ask", "what shipped?"])

    assert "Question" not in result.output


# ------------------------------------------------------------------ #
# output.format                                                       #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__ask__output_format_json_in_config__prints_the_json_body(tmp_path: Path, stub_ask: None) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(_config_data(output={"format": "json"})), encoding="utf-8")

    result = runner.invoke(cli_app.app, ["--config", str(p), "ask", "what shipped?"])

    assert '"answer": "The answer is 42."' in result.output


@pytest.mark.unit
def test__ask__output_format_plain_in_config__prints_the_answer(tmp_path: Path, stub_ask: None) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(_config_data(output={"format": "plain"})), encoding="utf-8")

    result = runner.invoke(cli_app.app, ["--config", str(p), "ask", "what shipped?"])

    assert "The answer is 42." in result.output


# ------------------------------------------------------------------ #
# Thread tree                                                         #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__ask__show_thread_tree_enabled__renders_the_tree(config_file: Path, stub_ask: None) -> None:
    result = runner.invoke(cli_app.app, ["--config", str(config_file), "ask", "what shipped?"])

    assert "auth migration" in result.output


@pytest.mark.unit
def test__ask__show_thread_tree_disabled__omits_the_tree(tmp_path: Path, stub_ask: None) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(_config_data(output={"show_thread_tree": False})), encoding="utf-8")

    result = runner.invoke(cli_app.app, ["--config", str(p), "ask", "what shipped?"])

    assert "auth migration" not in result.output


# ------------------------------------------------------------------ #
# logging.level                                                       #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__ask__logging_level_debug__applied_to_the_root_logger(tmp_path: Path, stub_ask: None) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(_config_data(logging={"level": "DEBUG"})), encoding="utf-8")

    runner.invoke(cli_app.app, ["--config", str(p), "ask", "what shipped?"])

    assert logging.getLogger().level == logging.DEBUG


@pytest.mark.unit
def test__ask__logging_level_error__applied_to_the_root_logger(tmp_path: Path, stub_ask: None) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(_config_data(logging={"level": "ERROR"})), encoding="utf-8")

    runner.invoke(cli_app.app, ["--config", str(p), "ask", "what shipped?"])

    assert logging.getLogger().level == logging.ERROR


# ------------------------------------------------------------------ #
# chat                                                                #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__chat__missing_config__exit_code_is_one(tmp_path: Path) -> None:
    result = runner.invoke(cli_app.app, ["--config", str(tmp_path / "nope.yaml"), "chat"])

    assert result.exit_code == 1


@pytest.mark.unit
def test__chat__missing_config__reports_the_error(tmp_path: Path) -> None:
    result = runner.invoke(cli_app.app, ["--config", str(tmp_path / "nope.yaml"), "chat"])

    assert "Configuration Error" in result.output


# ------------------------------------------------------------------ #
# config validate                                                     #
# ------------------------------------------------------------------ #


def _mock_endpoints(mm_status: int = 200, llm_status: int = 200) -> tuple[respx.Route, respx.Route]:
    mm_route = respx.get("https://mm.example.com/api/v4/users/me").mock(
        return_value=httpx.Response(mm_status, json={"id": "me001"})
    )
    llm_route = respx.get("https://llm.example.com/v1/models").mock(
        return_value=httpx.Response(llm_status, json={"object": "list", "data": []})
    )
    return mm_route, llm_route


@pytest.mark.unit
def test__config_validate__both_endpoints_reachable__exit_code_is_zero(config_file: Path) -> None:
    with respx.mock:
        _mock_endpoints()
        result = runner.invoke(cli_app.app, ["config", "validate", "--config", str(config_file)])

    assert result.exit_code == 0


@pytest.mark.unit
def test__config_validate__valid_config__calls_mattermost(config_file: Path) -> None:
    with respx.mock:
        mm_route, _ = _mock_endpoints()
        runner.invoke(cli_app.app, ["config", "validate", "--config", str(config_file)])

    assert mm_route.called


@pytest.mark.unit
def test__config_validate__valid_config__calls_the_llm_endpoint(config_file: Path) -> None:
    with respx.mock:
        _, llm_route = _mock_endpoints()
        runner.invoke(cli_app.app, ["config", "validate", "--config", str(config_file)])

    assert llm_route.called


@pytest.mark.unit
def test__config_validate__mattermost_rejects_the_token__exit_code_is_one(config_file: Path) -> None:
    with respx.mock:
        _mock_endpoints(mm_status=401)
        result = runner.invoke(cli_app.app, ["config", "validate", "--config", str(config_file)])

    assert result.exit_code == 1


@pytest.mark.unit
def test__config_validate__llm_rejects_the_key__exit_code_is_one(config_file: Path) -> None:
    with respx.mock:
        _mock_endpoints(llm_status=401)
        result = runner.invoke(cli_app.app, ["config", "validate", "--config", str(config_file)])

    assert result.exit_code == 1


@pytest.mark.unit
def test__config_validate__invalid_config__exit_code_is_one(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump({"mattermost": {"url": "https://mm.example.com"}}), encoding="utf-8")

    result = runner.invoke(cli_app.app, ["config", "validate", "--config", str(p)])

    assert result.exit_code == 1
