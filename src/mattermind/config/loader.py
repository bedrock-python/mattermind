"""Configuration loading with file + env + CLI override merging."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from mattermind.config.models import AppConfig


class ConfigError(Exception):
    """Raised when configuration is invalid or incomplete."""


# Pattern matches ${VAR} and ${VAR:-default}
_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")


def _interpolate_value(value: str) -> str:
    """Expand ${VAR} and ${VAR:-default} in a string value."""

    def replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default = match.group(2)  # None if no :-default
        env_val = os.environ.get(var_name)
        if env_val is not None:
            return env_val
        if default is not None:
            return default
        raise ConfigError(
            f"Environment variable '{var_name}' is required but not set. "
            f"Set it in your shell or add a default with ${{{var_name}:-default}}."
        )

    return _ENV_VAR_RE.sub(replacer, value)


def _interpolate_dict(data: Any) -> Any:
    """Recursively interpolate env vars in nested dict/list/str structures."""
    if isinstance(data, dict):
        return {k: _interpolate_dict(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_interpolate_dict(item) for item in data]
    if isinstance(data, str):
        return _interpolate_value(data)
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge override into base (in-place), recursively for nested dicts."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _env_overrides() -> dict[str, Any]:
    """Build override dict from MATTERMIND_* environment variables."""
    overrides: dict[str, Any] = {}

    env_map: dict[str, tuple[list[str], type[str] | type[int] | type[float]]] = {
        "MATTERMIND_MM_URL": (["mattermost", "url"], str),
        "MATTERMIND_MM_TOKEN": (["mattermost", "token"], str),
        "MATTERMIND_MM_LOGIN": (["mattermost", "login"], str),
        "MATTERMIND_MM_PASSWORD": (["mattermost", "password"], str),
        "MATTERMIND_TEAM": (["mattermost", "team"], str),
        "MATTERMIND_MM_VERIFY_SSL": (["mattermost", "verify_ssl"], str),
        "MATTERMIND_LLM_BASE_URL": (["llm", "base_url"], str),
        "MATTERMIND_LLM_API_KEY": (["llm", "api_key"], str),
        "MATTERMIND_MODEL": (["llm", "model"], str),
        "MATTERMIND_LLM_VERIFY_SSL": (["llm", "verify_ssl"], str),
    }

    for env_key, (path, cast) in env_map.items():
        raw = os.environ.get(env_key)
        if raw is not None:
            # Build nested dict from path
            node: dict[str, Any] = overrides
            for segment in path[:-1]:
                node = node.setdefault(segment, {})
            node[path[-1]] = cast(raw)

    return overrides


def load_config(
    config_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> AppConfig:
    """Load and merge configuration from all sources.

    Priority (lowest to highest):
      1. Pydantic defaults
      2. config.yaml file
      3. MATTERMIND_* environment variables
      4. explicit ``overrides`` dict (from CLI flags)
    """
    data: dict[str, Any] = {}

    # --- 1. Load YAML ---
    if config_path is not None:
        if not config_path.exists():
            raise ConfigError(f"Config file not found: {config_path}")
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ConfigError(f"Failed to parse config file {config_path}: {exc}") from exc

        if raw and isinstance(raw, dict):
            data = _interpolate_dict(raw)
    else:
        # Try default location
        default_path = Path.home() / ".config" / "mattermind" / "config.yaml"
        if default_path.exists():
            try:
                raw = yaml.safe_load(default_path.read_text(encoding="utf-8"))
                if raw and isinstance(raw, dict):
                    data = _interpolate_dict(raw)
            except (yaml.YAMLError, ConfigError):
                pass  # Silently ignore broken default config; env/CLI may still provide values

    # --- 2. Merge env vars ---
    env_data = _env_overrides()
    if env_data:
        data = _deep_merge(data, env_data)

    # --- 3. Merge CLI overrides ---
    if overrides:
        data = _deep_merge(data, overrides)

    # --- 4. Validate ---
    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        # Build a human-friendly error message
        lines = ["Configuration is invalid:"]
        for error in exc.errors():
            loc = " -> ".join(str(part) for part in error["loc"])
            msg = error["msg"]
            lines.append(f"  [{loc}] {msg}")
        lines.append("")
        lines.append("Set missing values in your config file, environment variables, or CLI flags.")
        lines.append("Run `mattermind init` to create a config file interactively.")
        raise ConfigError("\n".join(lines)) from exc
