"""Pydantic configuration models for mattermind."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class MattermostConfig(BaseModel):
    """Mattermost connection settings.

    Auth is either a personal access token (``token``) or a login/password pair.
    Exactly one of the two must be provided.
    """

    model_config = ConfigDict(extra="forbid")

    url: str
    team: str | None = None
    timeout_seconds: int = 30
    rate_limit_rps: int = 10
    verify_ssl: bool = True

    # Token-based auth
    token: str | None = None

    # Login/password auth
    login: str | None = None
    password: str | None = None

    @model_validator(mode="after")
    def _validate_auth(self) -> MattermostConfig:
        has_token = bool(self.token)
        has_login = bool(self.login) and bool(self.password)
        if not has_token and not has_login:
            raise ValueError(
                "Mattermost auth is not configured. Provide either 'token' or both 'login' and 'password'."
            )
        if has_token and has_login:
            raise ValueError("Provide either 'token' or 'login'+'password', not both.")
        return self

    def __repr__(self) -> str:
        if self.token:
            auth = "token=" + (self.token[:5] + "***" if len(self.token) > 5 else "***")
        else:
            auth = f"login={self.login!r}, password=***"
        team = f", team={self.team!r}" if self.team else ""
        return (
            f"MattermostConfig(url={self.url!r}, {auth}"
            f"{team}, timeout_seconds={self.timeout_seconds}, "
            f"rate_limit_rps={self.rate_limit_rps})"
        )

    def __str__(self) -> str:
        return self.__repr__()


class LLMConfig(BaseModel):
    """LLM provider settings."""

    model_config = ConfigDict(extra="forbid")

    base_url: str = "https://api.openai.com/v1"
    api_key: str
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    max_tokens_per_response: int = 4000
    request_timeout_seconds: int = 120
    verify_ssl: bool = True

    def __repr__(self) -> str:
        masked_key = self.api_key[:5] + "***" if len(self.api_key) > 5 else "***"
        return (
            f"LLMConfig(base_url={self.base_url!r}, api_key={masked_key!r}, "
            f"model={self.model!r}, temperature={self.temperature}, "
            f"max_tokens_per_response={self.max_tokens_per_response})"
        )

    def __str__(self) -> str:
        return self.__repr__()


class AgentConfig(BaseModel):
    """Agent loop behaviour settings."""

    model_config = ConfigDict(extra="forbid")

    max_iterations: int = 15
    max_threads_per_query: int = 20
    max_link_depth: int = 2
    total_token_budget: int = 200_000
    parallel_tool_calls: bool = True


class OutputConfig(BaseModel):
    """Output rendering settings."""

    model_config = ConfigDict(extra="forbid")

    show_thread_tree: bool = True
    show_token_usage: bool = True
    show_timings: bool = True
    format: Literal["markdown", "json", "plain"] = "markdown"


class LoggingConfig(BaseModel):
    """Logging settings."""

    model_config = ConfigDict(extra="forbid")

    level: str = "INFO"

    @field_validator("level", mode="after")
    @classmethod
    def _normalise_level(cls, value: str) -> str:
        level = value.upper()
        if level not in _LOG_LEVELS:
            raise ValueError(f"Unknown logging level {value!r}. Use one of: {', '.join(_LOG_LEVELS)}.")
        return level


class AppConfig(BaseModel):
    """Root application configuration."""

    model_config = ConfigDict(extra="forbid")

    mattermost: MattermostConfig
    llm: LLMConfig
    agent: AgentConfig = Field(default_factory=AgentConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
