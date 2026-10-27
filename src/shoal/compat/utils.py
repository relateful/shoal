"""Helpers bots reach for: finding things, snowflake times, invite links, and markdown.

    member = utils.get(guild.members, name="Ada")
    channel = utils.find(lambda channel: channel.name.startswith("log"), guild.channels)
    link = utils.oauth_url(application_id, permissions=Permissions(send_messages=True))

Discord: https://docs.discord.com/developers/reference#snowflakes
"""

import inspect
from collections.abc import Awaitable, Callable, Iterable, Iterator
from datetime import UTC, datetime
from typing import overload
from urllib.parse import urlencode

from shoal.core.clock import SystemClock
from shoal.core.formatting import escape_markdown, escape_mentions, format_dt, remove_markdown
from shoal.core.snowflake import Snowflake
from shoal.models.base import MISSING
from shoal.payloads.api import OAUTH_AUTHORIZE_URL
from shoal.payloads.application import ApplicationIntegrationType
from shoal.payloads.permissions import Permissions

__all__ = [
    "MISSING",
    "as_chunks",
    "escape_markdown",
    "escape_mentions",
    "find",
    "format_dt",
    "get",
    "maybe_coroutine",
    "oauth_url",
    "remove_markdown",
    "snowflake_time",
    "time_snowflake",
    "utcnow",
]


def find[T](predicate: Callable[[T], object], iterable: Iterable[T], /) -> T | None:
    """The first item `predicate` is true for, or `None`."""
    return next((item for item in iterable if predicate(item)), None)


def get[T](iterable: Iterable[T], /, **attributes: object) -> T | None:
    """The first item whose attributes have these values, or `None`.

    `channel__name="general"` looks at `item.channel.name`.
    """
    paths = [(name.split("__"), value) for name, value in attributes.items()]

    def matches(item: T) -> bool:
        for path, value in paths:
            found: object = item
            for part in path:
                found = getattr(found, part, MISSING)
            if found != value:
                return False
        return True

    return find(matches, iterable)


def as_chunks[T](iterable: Iterable[T], size: int) -> Iterator[list[T]]:
    """The items in lists of `size` (the last may be shorter).

    Raises:
        ValueError: `size` is not positive.
    """
    if size < 1:
        msg = f"chunks need a size of at least 1, not {size}"
        raise ValueError(msg)
    chunk: list[T] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


@overload
async def maybe_coroutine[T](
    function: Callable[..., Awaitable[T]], /, *args: object, **kwargs: object
) -> T: ...
@overload
async def maybe_coroutine[T](function: Callable[..., T], /, *args: object, **kwargs: object) -> T: ...
async def maybe_coroutine(function: Callable[..., object], /, *args: object, **kwargs: object) -> object:
    """The result of `function(*args, **kwargs)`, awaited if it is awaitable."""
    value = function(*args, **kwargs)
    return await value if inspect.isawaitable(value) else value


def snowflake_time(snowflake_id: int, /) -> datetime:
    """When the snowflake was made (when the user, message or channel was created)."""
    return Snowflake(snowflake_id).created_at


def time_snowflake(moment: datetime, /, *, high: bool = False) -> int:
    """The lowest snowflake made at `moment` (the highest with `high`): for paging by time."""
    return Snowflake.from_datetime(moment, high=high)


def utcnow() -> datetime:
    """Now, in UTC."""
    return datetime.fromtimestamp(SystemClock().wall(), tz=UTC)


def oauth_url(
    client_id: int,
    *,
    permissions: Permissions | None = None,
    guild: int | None = None,
    redirect_uri: str | None = None,
    scopes: Iterable[str] = ("bot", "applications.commands"),
    disable_guild_select: bool = False,
    state: str | None = None,
    integration_type: ApplicationIntegrationType | None = None,
) -> str:
    """The link that adds the bot to a guild (or installs the app), asking for `permissions`.

    `guild` preselects a guild, and `disable_guild_select` keeps it; `integration_type` installs to
    a guild or to a user's account.
    """
    query: dict[str, str] = {"client_id": str(client_id), "scope": " ".join(scopes)}
    if permissions is not None:
        query["permissions"] = str(int(permissions))
    if guild is not None:
        query["guild_id"] = str(guild)
    if disable_guild_select:
        query["disable_guild_select"] = "true"
    if redirect_uri is not None:
        query["redirect_uri"] = redirect_uri
        query["response_type"] = "code"
    if state is not None:
        query["state"] = state
    if integration_type is not None:
        query["integration_type"] = str(int(integration_type))
    return f"{OAUTH_AUTHORIZE_URL}?{urlencode(query)}"
