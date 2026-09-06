"""Top-level output models for mattermind."""

from pydantic import BaseModel


class TokenUsage(BaseModel):
    """Tracks LLM token consumption."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: "TokenUsage") -> "TokenUsage":
        """Return a new TokenUsage with combined counts."""
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


class AskResult(BaseModel):
    """Output schema for a completed ask command."""

    answer: str
    threads_explored: int
    tool_calls_made: int
    token_usage: TokenUsage
    elapsed_seconds: float
    incomplete: bool = False
    permalinks: list[str] = []
    explored_threads: list[dict[str, str]] = []
    """One entry per thread read: ``post_id``, ``channel``, ``title``, ``permalink``."""
