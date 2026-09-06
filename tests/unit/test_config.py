from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mattermind.config.loader import ConfigError, load_config
from mattermind.config.models import AppConfig


@pytest.fixture()
def base_config_data() -> dict[str, Any]:
    return {
        "mattermost": {
            "url": "https://mm.example.com",
            "token": "file_token_abc",
            "team": "engineering",
        },
        "llm": {
            "api_key": "file_llm_key_xyz",
            "model": "gpt-4o",
        },
    }


@pytest.fixture()
def config_file(tmp_path: Path, base_config_data: dict[str, Any]) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(base_config_data), encoding="utf-8")
    return p


def _write_yaml(tmp_path: Path, data: dict[str, Any]) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


# ------------------------------------------------------------------ #
# Basic loading                                                       #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__load_config__valid_file__returns_app_config(config_file: Path) -> None:
    result = load_config(config_path=config_file)

    assert isinstance(result, AppConfig)


@pytest.mark.unit
def test__load_config__valid_file__mattermost_url_matches(config_file: Path) -> None:
    result = load_config(config_path=config_file)

    assert result.mattermost.url == "https://mm.example.com"


@pytest.mark.unit
def test__load_config__valid_file__token_matches(config_file: Path) -> None:
    result = load_config(config_path=config_file)

    assert result.mattermost.token == "file_token_abc"  # noqa: S105


@pytest.mark.unit
def test__load_config__valid_file__model_matches(config_file: Path) -> None:
    result = load_config(config_path=config_file)

    assert result.llm.model == "gpt-4o"


@pytest.mark.unit
def test__load_config__missing_file__raises_config_error() -> None:
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(config_path=Path("/nonexistent/path/config.yaml"))


@pytest.mark.unit
def test__load_config__missing_required_field__raises_config_error(tmp_path: Path) -> None:
    data: dict[str, Any] = {
        "mattermost": {"url": "https://mm.example.com", "token": "tok"},
    }
    p = _write_yaml(tmp_path, data)

    with pytest.raises(ConfigError, match="Configuration is invalid"):
        load_config(config_path=p)


# ------------------------------------------------------------------ #
# Priority: defaults < file < env < CLI                               #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__load_config__env_var_set__overrides_file_model(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATTERMIND_MODEL", "gpt-3.5-turbo")

    result = load_config(config_path=config_file)

    assert result.llm.model == "gpt-3.5-turbo"


@pytest.mark.unit
def test__load_config__cli_override_set__overrides_env_model(
    config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MATTERMIND_MODEL", "gpt-3.5-turbo")

    result = load_config(config_path=config_file, overrides={"llm": {"model": "gpt-4-turbo"}})

    assert result.llm.model == "gpt-4-turbo"


@pytest.mark.unit
def test__load_config__env_token_set__overrides_file_token(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATTERMIND_MM_TOKEN", "env_token_override")

    result = load_config(config_path=config_file)

    assert result.mattermost.token == "env_token_override"  # noqa: S105


# ------------------------------------------------------------------ #
# Env interpolation                                                   #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__load_config__interpolated_token__resolves_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_MM_TOKEN", "interpolated_token")
    data: dict[str, Any] = {
        "mattermost": {
            "url": "https://mm.example.com",
            "token": "${MY_MM_TOKEN}",
            "team": "engineering",
        },
        "llm": {"api_key": "sk-test"},
    }
    p = _write_yaml(tmp_path, data)

    result = load_config(config_path=p)

    assert result.mattermost.token == "interpolated_token"  # noqa: S105


@pytest.mark.unit
def test__load_config__interpolated_var_with_default__uses_default_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MISSING_VAR", raising=False)
    data: dict[str, Any] = {
        "mattermost": {
            "url": "https://mm.example.com",
            "token": "tok",
            "team": "${MISSING_VAR:-default_team}",
        },
        "llm": {"api_key": "sk-test"},
    }
    p = _write_yaml(tmp_path, data)

    result = load_config(config_path=p)

    assert result.mattermost.team == "default_team"


@pytest.mark.unit
def test__load_config__interpolated_required_var_missing__raises_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REQUIRED_VAR", raising=False)
    data: dict[str, Any] = {
        "mattermost": {
            "url": "https://mm.example.com",
            "token": "${REQUIRED_VAR}",
            "team": "eng",
        },
        "llm": {"api_key": "sk-test"},
    }
    p = _write_yaml(tmp_path, data)

    with pytest.raises(ConfigError, match="REQUIRED_VAR"):
        load_config(config_path=p)


# ------------------------------------------------------------------ #
# Token masking in repr                                               #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__mattermost_config__repr__masks_full_token(config_file: Path) -> None:
    cfg = load_config(config_path=config_file)

    r = repr(cfg.mattermost)

    assert "file_token_abc" not in r


@pytest.mark.unit
def test__mattermost_config__repr__shows_token_prefix(config_file: Path) -> None:
    cfg = load_config(config_path=config_file)

    r = repr(cfg.mattermost)

    assert "file_***" in r


@pytest.mark.unit
def test__llm_config__repr__masks_full_api_key(config_file: Path) -> None:
    cfg = load_config(config_path=config_file)

    r = repr(cfg.llm)

    assert "file_llm_key_xyz" not in r


@pytest.mark.unit
def test__llm_config__repr__shows_key_prefix(config_file: Path) -> None:
    cfg = load_config(config_path=config_file)

    r = repr(cfg.llm)

    assert "file_***" in r


@pytest.mark.unit
def test__mattermost_config__str__equals_repr(config_file: Path) -> None:
    cfg = load_config(config_path=config_file)

    assert str(cfg.mattermost) == repr(cfg.mattermost)


@pytest.mark.unit
def test__llm_config__str__equals_repr(config_file: Path) -> None:
    cfg = load_config(config_path=config_file)

    assert str(cfg.llm) == repr(cfg.llm)


# ------------------------------------------------------------------ #
# Defaults                                                            #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__load_config__no_agent_section__applies_default_max_iterations(config_file: Path) -> None:
    result = load_config(config_path=config_file)

    assert result.agent.max_iterations == 15


@pytest.mark.unit
def test__load_config__no_agent_section__applies_default_token_budget(config_file: Path) -> None:
    result = load_config(config_path=config_file)

    assert result.agent.total_token_budget == 200_000


@pytest.mark.unit
def test__load_config__no_output_section__applies_default_format(config_file: Path) -> None:
    result = load_config(config_path=config_file)

    assert result.output.format == "markdown"


# ------------------------------------------------------------------ #
# Interpolation error message                                         #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__load_config__interpolated_required_var_missing__hint_names_the_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REQUIRED_VAR", raising=False)
    data: dict[str, Any] = {
        "mattermost": {
            "url": "https://mm.example.com",
            "token": "${REQUIRED_VAR}",
            "team": "eng",
        },
        "llm": {"api_key": "sk-test"},
    }
    p = _write_yaml(tmp_path, data)

    with pytest.raises(ConfigError) as excinfo:
        load_config(config_path=p)

    assert "${REQUIRED_VAR:-default}" in str(excinfo.value)


# ------------------------------------------------------------------ #
# Unknown keys                                                        #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__load_config__misspelled_key_in_section__raises_config_error(
    tmp_path: Path, base_config_data: dict[str, Any]
) -> None:
    base_config_data["mattermost"]["tiemout_seconds"] = 60
    p = _write_yaml(tmp_path, base_config_data)

    with pytest.raises(ConfigError, match="tiemout_seconds"):
        load_config(config_path=p)


@pytest.mark.unit
def test__load_config__unknown_top_level_section__raises_config_error(
    tmp_path: Path, base_config_data: dict[str, Any]
) -> None:
    base_config_data["outupt"] = {"format": "plain"}
    p = _write_yaml(tmp_path, base_config_data)

    with pytest.raises(ConfigError, match="outupt"):
        load_config(config_path=p)


# ------------------------------------------------------------------ #
# output.format                                                       #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__load_config__output_format_json__is_accepted(tmp_path: Path, base_config_data: dict[str, Any]) -> None:
    base_config_data["output"] = {"format": "json"}
    p = _write_yaml(tmp_path, base_config_data)

    result = load_config(config_path=p)

    assert result.output.format == "json"


@pytest.mark.unit
def test__load_config__unknown_output_format__raises_config_error(
    tmp_path: Path, base_config_data: dict[str, Any]
) -> None:
    base_config_data["output"] = {"format": "markdwon"}
    p = _write_yaml(tmp_path, base_config_data)

    with pytest.raises(ConfigError, match="output -> format"):
        load_config(config_path=p)


# ------------------------------------------------------------------ #
# logging.level                                                       #
# ------------------------------------------------------------------ #


@pytest.mark.unit
def test__load_config__lowercase_logging_level__is_normalised(tmp_path: Path, base_config_data: dict[str, Any]) -> None:
    base_config_data["logging"] = {"level": "debug"}
    p = _write_yaml(tmp_path, base_config_data)

    result = load_config(config_path=p)

    assert result.logging.level == "DEBUG"


@pytest.mark.unit
def test__load_config__unknown_logging_level__raises_config_error(
    tmp_path: Path, base_config_data: dict[str, Any]
) -> None:
    base_config_data["logging"] = {"level": "chatty"}
    p = _write_yaml(tmp_path, base_config_data)

    with pytest.raises(ConfigError, match="Unknown logging level"):
        load_config(config_path=p)
