"""Pydantic domain models for Mattermost API responses."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel


class Team(BaseModel):
    """A Mattermost team."""

    id: str
    name: str  # slug used in URLs and config
    display_name: str
    description: str = ""
    type: str = ""  # "O" = open, "I" = invite-only


class User(BaseModel):
    """Mattermost user."""

    id: str
    username: str
    first_name: str = ""
    last_name: str = ""
    nickname: str = ""
    position: str = ""

    @property
    def display_name(self) -> str:
        """Return the most human-readable name available."""
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.nickname or self.username


class Post(BaseModel):
    """A single Mattermost post."""

    id: str
    create_at: int  # millisecond epoch timestamp
    user_id: str
    channel_id: str
    message: str
    root_id: str = ""

    @property
    def created_at(self) -> datetime:
        """Return timezone-aware UTC datetime."""
        return datetime.fromtimestamp(self.create_at / 1000, tz=UTC)


class Thread(BaseModel):
    """A Mattermost thread (root post + all replies), ordered by create_at."""

    root_post_id: str
    posts: list[Post]  # ordered ascending by create_at


class SearchHit(BaseModel):
    """A post returned from the Mattermost search API."""

    post_id: str
    message: str
    channel_id: str
    channel_name: str
    user_id: str
    username: str = ""
    permalink: str = ""
