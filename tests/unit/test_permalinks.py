from __future__ import annotations

import pytest

from mattermind.agent.tools import parse_post_id_from_permalink


@pytest.mark.unit
@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "https://mm.company.com/engineering/pl/abc123def456ghi789jklmno",
            "abc123def456ghi789jklmno",
        ),
        (
            "https://mm.company.com/engineering/pl/abc123def456ghi789jklmno/",
            "abc123def456ghi789jklmno",
        ),
        (
            "https://mm.company.com/engineering/pl/abc123def456ghi789jklmno?referrer=slack",
            "abc123def456ghi789jklmno",
        ),
        (
            "https://chat.internal.corp/myteam/pl/zyxwvutsrqponmlkjihgfedcba",
            "zyxwvutsrqponmlkjihgfedcba",
        ),
        (
            "https://mm.example.com/team/pl/abcdefghijklmnopqrstuvwxyz",
            "abcdefghijklmnopqrstuvwxyz",
        ),
        (
            "https://mm.example.com/team/pl/ABC123abc456DEF789xyz00000",
            "ABC123abc456DEF789xyz00000",
        ),
    ],
)
def test__parse_post_id_from_permalink__valid_url__returns_post_id(url: str, expected: str) -> None:
    result = parse_post_id_from_permalink(url)

    assert result == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "url",
    [
        "https://mm.company.com/engineering/channels/general",
        "https://mm.company.com/engineering/abc123def456",
        "",
        "abc123def456",
        "https://mm.company.com/team/pl/short",
        "https://example.com/foo/bar/baz",
    ],
)
def test__parse_post_id_from_permalink__invalid_url__returns_none(url: str) -> None:
    result = parse_post_id_from_permalink(url)

    assert result is None
