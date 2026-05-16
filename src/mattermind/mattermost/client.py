"""Async Mattermost REST API v4 client with retries and rate limiting."""

from __future__ import annotations

import asyncio
import logging
from types import TracebackType
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from mattermind.config.models import MattermostConfig
from mattermind.mattermost.models import Post, SearchHit, Team, Thread, User

logger = logging.getLogger(__name__)


class MattermostAPIError(Exception):
    """Raised when the Mattermost API returns an error response."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"Mattermost API error {status_code}: {message}")


def _should_retry(exc: BaseException) -> bool:
    """Retry on 5xx errors and 429 (rate limit), but NOT on other 4xx."""
    if isinstance(exc, MattermostAPIError):
        return exc.status_code == 429 or exc.status_code >= 500
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError))


class MattermostClient:
    """Async HTTP client for Mattermost REST API v4.

    Usage::

        async with MattermostClient(config) as client:
            hits = await client.search_posts(team_id, "incident", None, 20)
    """

    def __init__(self, config: MattermostConfig) -> None:
        self._config = config
        self._base_url = config.url.rstrip("/")
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if config.token:
            self._headers["Authorization"] = f"Bearer {config.token}"
        self._semaphore = asyncio.Semaphore(config.rate_limit_rps)
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> MattermostClient:
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=self._config.timeout_seconds,
            verify=self._config.verify_ssl,
        )
        if not self._config.token:
            await self._login()
        return self

    async def _login(self) -> None:
        """Authenticate with login/password and store the session token."""
        assert self._http is not None
        response = await self._http.post(
            "/api/v4/users/login",
            json={"login_id": self._config.login, "password": self._config.password},
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("message", response.text)
            except Exception:
                detail = response.text
            raise MattermostAPIError(response.status_code, detail)

        token = response.headers.get("Token")
        if not token:
            raise MattermostAPIError(0, "Login succeeded but no Token header returned.")

        assert self._http is not None
        self._http.headers["Authorization"] = f"Bearer {token}"
        logger.debug("Authenticated via login/password, session token obtained.")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    @property
    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError("MattermostClient must be used as an async context manager.")
        return self._http

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        """Execute a rate-limited, retried HTTP request and return parsed JSON."""

        @retry(
            retry=retry_if_exception(_should_retry),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            reraise=True,
        )
        async def _inner() -> Any:
            async with self._semaphore:
                logger.debug("%s %s", method.upper(), path)
                response = await self._client.request(method, path, **kwargs)

            if response.status_code >= 400:
                try:
                    detail = response.json().get("message", response.text)
                except Exception:
                    detail = response.text
                raise MattermostAPIError(response.status_code, detail)

            if response.status_code == 204 or not response.content:
                return {}

            return response.json()

        return await _inner()

    # ------------------------------------------------------------------ #
    # Public API methods                                                   #
    # ------------------------------------------------------------------ #

    async def get_my_teams(self) -> list[Team]:
        """Return all teams the current user belongs to."""
        data: list[dict[str, Any]] = await self._request("GET", "/api/v4/users/me/teams")
        return [Team.model_validate(t) for t in data]

    async def validate_connection(self) -> bool:
        """Return True if the token is valid and the server is reachable."""
        try:
            await self._request("GET", "/api/v4/users/me")
        except Exception:
            return False
        else:
            return True

    async def get_team_id(self, team_name_or_id: str) -> str:
        """Resolve a team name or ID to a team ID string."""
        try:
            data: dict[str, Any] = await self._request("GET", f"/api/v4/teams/name/{team_name_or_id}")
            return str(data["id"])
        except MattermostAPIError as exc:
            if exc.status_code == 404:
                # Maybe it was already an ID — validate it
                try:
                    data = await self._request("GET", f"/api/v4/teams/{team_name_or_id}")
                    return str(data["id"])
                except MattermostAPIError:
                    pass
            raise

    async def search_posts(
        self,
        team_id: str,
        query: str,
        channel_id: str | None = None,
        per_page: int = 20,
    ) -> list[SearchHit]:
        """Full-text search for posts within a team."""
        payload: dict[str, Any] = {"terms": query, "is_or_search": False, "per_page": per_page}
        if channel_id:
            payload["channel_id"] = channel_id

        data: dict[str, Any] = await self._request(
            "POST",
            f"/api/v4/teams/{team_id}/posts/search",
            json=payload,
        )

        order: list[str] = data.get("order", [])
        posts_map: dict[str, Any] = data.get("posts", {})

        # Fetch channel names in parallel (one request per unique channel_id)
        unique_channel_ids: set[str] = {posts_map[pid]["channel_id"] for pid in order if pid in posts_map}
        channel_names: dict[str, str] = {}
        if unique_channel_ids:
            results = await asyncio.gather(
                *[self.get_channel(cid) for cid in unique_channel_ids],
                return_exceptions=True,
            )
            for cid, result in zip(unique_channel_ids, results, strict=False):
                if isinstance(result, dict):
                    channel_names[cid] = result.get("name", cid)
                else:
                    channel_names[cid] = cid

        hits: list[SearchHit] = []
        for post_id in order:
            if post_id not in posts_map:
                continue
            raw = posts_map[post_id]
            cid = raw.get("channel_id", "")
            hits.append(
                SearchHit(
                    post_id=post_id,
                    message=raw.get("message", ""),
                    channel_id=cid,
                    channel_name=channel_names.get(cid, cid),
                    user_id=raw.get("user_id", ""),
                )
            )

        return hits

    async def get_thread(self, post_id: str) -> Thread:
        """Fetch the complete thread containing post_id."""
        data: dict[str, Any] = await self._request(
            "GET",
            f"/api/v4/posts/{post_id}/thread",
            params={"skipFetchThreads": "false", "collapsedThreads": "false"},
        )

        posts_map: dict[str, Any] = data.get("posts", {})
        posts: list[Post] = []
        for raw in posts_map.values():
            try:
                posts.append(Post.model_validate(raw))
            except Exception as exc:
                logger.warning("Failed to parse post %s: %s", raw.get("id"), exc)

        posts.sort(key=lambda p: p.create_at)

        # The root post is the one with no root_id
        root_id = next(
            (p.id for p in posts if not p.root_id),
            posts[0].id if posts else post_id,
        )

        return Thread(root_post_id=root_id, posts=posts)

    async def get_user(self, user_id: str) -> User:
        """Fetch a user by ID."""
        data: dict[str, Any] = await self._request("GET", f"/api/v4/users/{user_id}")
        return User.model_validate(data)

    async def get_channel(self, channel_id: str) -> dict[str, str]:
        """Fetch channel metadata by ID."""
        data: dict[str, Any] = await self._request("GET", f"/api/v4/channels/{channel_id}")
        return {k: str(v) for k, v in data.items()}
