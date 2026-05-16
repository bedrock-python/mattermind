from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from mattermind.config.models import MattermostConfig
from mattermind.mattermost.client import MattermostAPIError, MattermostClient
from mattermind.mattermost.models import Thread, User


@pytest.fixture()
def mm_config() -> MattermostConfig:
    return MattermostConfig(
        url="https://mm.example.com",
        token="test-token-12345",  # noqa: S106
        team="engineering",
        timeout_seconds=10,
        rate_limit_rps=5,
    )


def _post_data(
    post_id: str = "post001",
    root_id: str = "",
    message: str = "hello",
    user_id: str = "user001",
    channel_id: str = "chan001",
    create_at: int = 1_700_000_000_000,
) -> dict[str, Any]:
    return {
        "id": post_id,
        "create_at": create_at,
        "user_id": user_id,
        "channel_id": channel_id,
        "message": message,
        "root_id": root_id,
    }


# ------------------------------------------------------------------ #
# validate_connection                                                  #
# ------------------------------------------------------------------ #


@pytest.mark.unit
@pytest.mark.asyncio
async def test__validate_connection__ok_response__returns_true(mm_config: MattermostConfig) -> None:
    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/users/me").mock(return_value=httpx.Response(200, json={"id": "me001"}))
        async with MattermostClient(mm_config) as client:
            result = await client.validate_connection()

    assert result is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test__validate_connection__unauthorized_response__returns_false(mm_config: MattermostConfig) -> None:
    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/users/me").mock(return_value=httpx.Response(401, json={"message": "Unauthorised"}))
        async with MattermostClient(mm_config) as client:
            result = await client.validate_connection()

    assert result is False


# ------------------------------------------------------------------ #
# get_user                                                            #
# ------------------------------------------------------------------ #


@pytest.mark.unit
@pytest.mark.asyncio
async def test__get_user__valid_response__returns_user_instance(mm_config: MattermostConfig) -> None:
    user_data = {
        "id": "user001",
        "username": "jdoe",
        "first_name": "John",
        "last_name": "Doe",
        "nickname": "",
        "position": "Engineer",
    }
    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/users/user001").mock(return_value=httpx.Response(200, json=user_data))
        async with MattermostClient(mm_config) as client:
            result = await client.get_user("user001")

    assert isinstance(result, User)


@pytest.mark.unit
@pytest.mark.asyncio
async def test__get_user__first_and_last_name_set__display_name_is_full_name(mm_config: MattermostConfig) -> None:
    user_data = {
        "id": "user001",
        "username": "jdoe",
        "first_name": "John",
        "last_name": "Doe",
        "nickname": "",
        "position": "Engineer",
    }
    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/users/user001").mock(return_value=httpx.Response(200, json=user_data))
        async with MattermostClient(mm_config) as client:
            result = await client.get_user("user001")

    assert result.display_name == "John Doe"


@pytest.mark.unit
@pytest.mark.asyncio
async def test__get_user__no_name_but_nickname__display_name_falls_back_to_nickname(
    mm_config: MattermostConfig,
) -> None:
    user_data = {
        "id": "user002",
        "username": "anon",
        "first_name": "",
        "last_name": "",
        "nickname": "The Shadow",
        "position": "",
    }
    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/users/user002").mock(return_value=httpx.Response(200, json=user_data))
        async with MattermostClient(mm_config) as client:
            result = await client.get_user("user002")

    assert result.display_name == "The Shadow"


# ------------------------------------------------------------------ #
# get_thread                                                          #
# ------------------------------------------------------------------ #


@pytest.mark.unit
@pytest.mark.asyncio
async def test__get_thread__valid_response__returns_thread_instance(mm_config: MattermostConfig) -> None:
    root = _post_data("root001", message="Root message")
    thread_data = {
        "order": ["root001"],
        "posts": {"root001": root},
    }
    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/posts/root001/thread").mock(return_value=httpx.Response(200, json=thread_data))
        async with MattermostClient(mm_config) as client:
            result = await client.get_thread("root001")

    assert isinstance(result, Thread)


@pytest.mark.unit
@pytest.mark.asyncio
async def test__get_thread__three_posts__root_post_id_matches(mm_config: MattermostConfig) -> None:
    root = _post_data("root001", message="Root message", create_at=1_700_000_001_000)
    reply1 = _post_data("reply001", root_id="root001", message="Reply 1", create_at=1_700_000_002_000)
    reply2 = _post_data("reply002", root_id="root001", message="Reply 2", create_at=1_700_000_003_000)
    thread_data = {
        "order": ["root001", "reply001", "reply002"],
        "posts": {"root001": root, "reply001": reply1, "reply002": reply2},
    }
    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/posts/root001/thread").mock(return_value=httpx.Response(200, json=thread_data))
        async with MattermostClient(mm_config) as client:
            result = await client.get_thread("root001")

    assert result.root_post_id == "root001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test__get_thread__three_posts__all_posts_present(mm_config: MattermostConfig) -> None:
    root = _post_data("root001", message="Root message", create_at=1_700_000_001_000)
    reply1 = _post_data("reply001", root_id="root001", message="Reply 1", create_at=1_700_000_002_000)
    reply2 = _post_data("reply002", root_id="root001", message="Reply 2", create_at=1_700_000_003_000)
    thread_data = {
        "order": ["root001", "reply001", "reply002"],
        "posts": {"root001": root, "reply001": reply1, "reply002": reply2},
    }
    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/posts/root001/thread").mock(return_value=httpx.Response(200, json=thread_data))
        async with MattermostClient(mm_config) as client:
            result = await client.get_thread("root001")

    assert len(result.posts) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test__get_thread__posts_out_of_order__sorted_by_create_at(mm_config: MattermostConfig) -> None:
    post_a = _post_data("postA", message="A", create_at=1_700_000_003_000)
    post_b = _post_data("postB", root_id="postA", message="B", create_at=1_700_000_001_000)
    post_c = _post_data("postC", root_id="postA", message="C", create_at=1_700_000_002_000)
    thread_data = {
        "order": ["postA", "postC", "postB"],
        "posts": {"postA": post_a, "postB": post_b, "postC": post_c},
    }
    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/posts/postA/thread").mock(return_value=httpx.Response(200, json=thread_data))
        async with MattermostClient(mm_config) as client:
            result = await client.get_thread("postA")

    assert [p.id for p in result.posts] == ["postB", "postC", "postA"]


# ------------------------------------------------------------------ #
# Retry behaviour                                                     #
# ------------------------------------------------------------------ #


@pytest.mark.unit
@pytest.mark.asyncio
async def test__get__5xx_then_success__retries_and_returns_true(mm_config: MattermostConfig) -> None:
    call_count = 0

    def side_effect(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(503, json={"message": "Service Unavailable"})
        return httpx.Response(200, json={"id": "me001"})

    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/users/me").mock(side_effect=side_effect)
        async with MattermostClient(mm_config) as client:
            result = await client.validate_connection()

    assert result is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test__get__5xx_then_success__called_three_times(mm_config: MattermostConfig) -> None:
    call_count = 0

    def side_effect(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(503, json={"message": "Service Unavailable"})
        return httpx.Response(200, json={"id": "me001"})

    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/users/me").mock(side_effect=side_effect)
        async with MattermostClient(mm_config) as client:
            await client.validate_connection()

    assert call_count == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test__get__429_then_success__retries_and_returns_true(mm_config: MattermostConfig) -> None:
    call_count = 0

    def side_effect(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, json={"message": "Too Many Requests"})
        return httpx.Response(200, json={"id": "me001"})

    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/users/me").mock(side_effect=side_effect)
        async with MattermostClient(mm_config) as client:
            result = await client.validate_connection()

    assert result is True
    assert call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test__get__401_response__raises_mattermost_api_error(mm_config: MattermostConfig) -> None:
    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/users/user001").mock(return_value=httpx.Response(401, json={"message": "Unauthorised"}))
        async with MattermostClient(mm_config) as client:
            with pytest.raises(MattermostAPIError) as exc_info:
                await client.get_user("user001")

    assert exc_info.value.status_code == 401


@pytest.mark.unit
@pytest.mark.asyncio
async def test__get__401_response__no_retry(mm_config: MattermostConfig) -> None:
    call_count = 0

    def side_effect(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, json={"message": "Unauthorised"})

    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/users/user001").mock(side_effect=side_effect)
        async with MattermostClient(mm_config) as client:
            with pytest.raises(MattermostAPIError):
                await client.get_user("user001")

    assert call_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test__get__404_response__raises_mattermost_api_error(mm_config: MattermostConfig) -> None:
    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/users/user999").mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
        async with MattermostClient(mm_config) as client:
            with pytest.raises(MattermostAPIError) as exc_info:
                await client.get_user("user999")

    assert exc_info.value.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
async def test__get__404_response__no_retry(mm_config: MattermostConfig) -> None:
    call_count = 0

    def side_effect(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(404, json={"message": "Not Found"})

    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.get("/api/v4/users/user999").mock(side_effect=side_effect)
        async with MattermostClient(mm_config) as client:
            with pytest.raises(MattermostAPIError):
                await client.get_user("user999")

    assert call_count == 1


# ------------------------------------------------------------------ #
# search_posts                                                        #
# ------------------------------------------------------------------ #


@pytest.mark.unit
@pytest.mark.asyncio
async def test__search_posts__two_results__returns_two_hits(mm_config: MattermostConfig) -> None:
    post1 = _post_data("post001", message="incident report", channel_id="chan001")
    post2 = _post_data("post002", message="related discussion", channel_id="chan001")
    search_resp: dict[str, Any] = {
        "order": ["post001", "post002"],
        "posts": {"post001": post1, "post002": post2},
    }
    channel_resp = {"id": "chan001", "name": "general", "display_name": "General"}

    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.post("/api/v4/teams/team001/posts/search").mock(return_value=httpx.Response(200, json=search_resp))
        mock.get("/api/v4/channels/chan001").mock(return_value=httpx.Response(200, json=channel_resp))
        async with MattermostClient(mm_config) as client:
            hits = await client.search_posts("team001", "incident", per_page=10)

    assert len(hits) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test__search_posts__two_results__post_ids_match(mm_config: MattermostConfig) -> None:
    post1 = _post_data("post001", message="incident report", channel_id="chan001")
    post2 = _post_data("post002", message="related discussion", channel_id="chan001")
    search_resp: dict[str, Any] = {
        "order": ["post001", "post002"],
        "posts": {"post001": post1, "post002": post2},
    }
    channel_resp = {"id": "chan001", "name": "general", "display_name": "General"}

    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.post("/api/v4/teams/team001/posts/search").mock(return_value=httpx.Response(200, json=search_resp))
        mock.get("/api/v4/channels/chan001").mock(return_value=httpx.Response(200, json=channel_resp))
        async with MattermostClient(mm_config) as client:
            hits = await client.search_posts("team001", "incident", per_page=10)

    assert hits[0].post_id == "post001"
    assert hits[1].post_id == "post002"


@pytest.mark.unit
@pytest.mark.asyncio
async def test__search_posts__two_results__channel_name_resolved(mm_config: MattermostConfig) -> None:
    post1 = _post_data("post001", message="incident report", channel_id="chan001")
    search_resp: dict[str, Any] = {
        "order": ["post001"],
        "posts": {"post001": post1},
    }
    channel_resp = {"id": "chan001", "name": "general", "display_name": "General"}

    with respx.mock(base_url="https://mm.example.com") as mock:
        mock.post("/api/v4/teams/team001/posts/search").mock(return_value=httpx.Response(200, json=search_resp))
        mock.get("/api/v4/channels/chan001").mock(return_value=httpx.Response(200, json=channel_resp))
        async with MattermostClient(mm_config) as client:
            hits = await client.search_posts("team001", "incident", per_page=10)

    assert hits[0].channel_name == "general"
