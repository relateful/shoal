from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from shoal.compat.utils import (
    as_chunks,
    find,
    get,
    maybe_coroutine,
    oauth_url,
    snowflake_time,
    time_snowflake,
    utcnow,
)
from shoal.payloads import ApplicationIntegrationType, Permissions


@dataclass(frozen=True)
class Place:
    name: str


@dataclass(frozen=True)
class Person:
    name: str
    home: Place


PEOPLE = [Person("ada", Place("london")), Person("grace", Place("new york"))]


def test_find_and_get_return_the_first_match() -> None:
    assert find(lambda person: person.name.startswith("g"), PEOPLE) is PEOPLE[1]
    assert find(lambda person: person.name == "nobody", PEOPLE) is None
    assert get(PEOPLE, name="ada") is PEOPLE[0]
    assert get(PEOPLE, home__name="new york") is PEOPLE[1]
    assert get(PEOPLE, name="ada", home__name="new york") is None
    assert get(PEOPLE, missing="x") is None


def test_chunks_have_the_size_asked_for() -> None:
    assert list(as_chunks(range(5), 2)) == [[0, 1], [2, 3], [4]]
    assert list(as_chunks(list[int](), 3)) == []
    with pytest.raises(ValueError, match="at least 1"):
        list(as_chunks(range(3), 0))


async def test_maybe_coroutine_awaits_only_awaitables() -> None:
    async def doubled(value: int) -> int:
        return value * 2

    def tripled(value: int) -> int:
        return value * 3

    assert await maybe_coroutine(doubled, 2) == 4
    assert await maybe_coroutine(tripled, value=2) == 6


def test_snowflakes_and_times_convert_both_ways() -> None:
    moment = datetime(2021, 4, 20, 21, 20, 30, tzinfo=UTC)
    low = time_snowflake(moment)
    assert snowflake_time(low) == moment
    assert time_snowflake(moment, high=True) > low
    assert utcnow().tzinfo is UTC


def test_oauth_urls_carry_every_option_given() -> None:
    plain = urlsplit(oauth_url(123))
    assert (plain.scheme, plain.netloc, plain.path) == ("https", "discord.com", "/oauth2/authorize")
    assert parse_qs(plain.query) == {"client_id": ["123"], "scope": ["bot applications.commands"]}
    full = oauth_url(
        123,
        permissions=Permissions(send_messages=True),
        guild=456,
        redirect_uri="https://example.com/back",
        scopes=["bot"],
        disable_guild_select=True,
        state="xyz",
        integration_type=ApplicationIntegrationType.USER_INSTALL,
    )
    assert parse_qs(urlsplit(full).query) == {
        "client_id": ["123"],
        "scope": ["bot"],
        "permissions": [str(int(Permissions(send_messages=True)))],
        "guild_id": ["456"],
        "disable_guild_select": ["true"],
        "redirect_uri": ["https://example.com/back"],
        "response_type": ["code"],
        "state": ["xyz"],
        "integration_type": ["1"],
    }
