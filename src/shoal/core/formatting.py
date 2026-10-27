r"""Discord's message formatting: mentions, timestamps, and the markdown subset clients render.

    format_dt(event.start, "R")      # "<t:1618953630:R>", shown as "in 3 days"
    escape_markdown("**not bold**")  # \*\*not bold\*\*, shown as typed
    escape_mentions("@everyone")     # cannot ping anyone

Discord: https://docs.discord.com/developers/reference#message-formatting
"""

import re
from datetime import datetime
from typing import Final, Literal

ANY_MENTION: Final = re.compile(r"<(@[!&]?|#)([0-9]{15,20})>")
"""A user, role or channel mention; group 1 is `@`, `@!`, `@&` or `#`, group 2 the ID.

Discord: https://docs.discord.com/developers/reference#message-formatting
"""

CHANNEL_MENTION: Final = re.compile(r"<#([0-9]{15,20})>")
"""A channel mention, `<#id>`; group 1 is the ID.

Discord: https://docs.discord.com/developers/reference#message-formatting
"""

CUSTOM_EMOJI: Final = re.compile(r"<(a?):([A-Za-z0-9_]{1,32}):([0-9]{15,20})>")
"""A custom emoji, `<:name:id>` or `<a:name:id>`; groups are `a` (animated) or empty, name, ID.

Discord: https://docs.discord.com/developers/reference#message-formatting
"""

ROLE_MENTION: Final = re.compile(r"<@&([0-9]{15,20})>")
"""A role mention, `<@&id>`; group 1 is the ID.

Discord: https://docs.discord.com/developers/reference#message-formatting
"""

TIMESTAMP: Final = re.compile(r"<t:(-?[0-9]+)(?::([tTdDfFsSR]))?>")
"""A timestamp, `<t:seconds>` or `<t:seconds:style>`; groups are the seconds and the style.

Discord: https://docs.discord.com/developers/reference#message-formatting
"""

USER_MENTION: Final = re.compile(r"<@!?([0-9]{15,20})>")
"""A user mention, `<@id>` (or the deprecated `<@!id>`); group 1 is the ID.

Discord: https://docs.discord.com/developers/reference#message-formatting
"""

type TimestampStyle = Literal["t", "T", "d", "D", "f", "F", "s", "S", "R"]
"""How a client shows a timestamp: times (`t`, `T`), dates (`d`, `D`), both (`f`, `F`, `s`, `S`)
or relative (`R`, "in 3 days"). Without one, clients use `f`.

Discord: https://docs.discord.com/developers/reference#message-formatting-timestamp-styles
"""

_EVERYONE: Final = re.compile(r"@(everyone|here|[!&]?[0-9]{15,20})")
"""What pings: `@everyone`, `@here`, and the raw form of a user or role mention."""

_INLINE: Final = re.compile(r"[\\*_~`|]")
"""Characters that format text anywhere in a line."""

_LINE_START: Final = re.compile(
    r"^(?P<lead>[ \t]*)(?P<marker>>>>|>|#{1,3}|-#|[-*]|(?P<number>\d+)\.)(?P<space>[ \t])", re.MULTILINE
)
"""What formats a line when it starts it: quotes, headings, subtext and lists."""

_MASKED_LINK: Final = re.compile(r"\[(?P<text>[^\]\n]+)\]\((?P<target>[^)\s]+)\)")
"""A masked link, `[text](url)`."""

_URL: Final = re.compile(r"<[^: >]+:/[^ >]+>|(?:https?|steam)://[^\s<]+[^<.,:;\"'\]\s]")
"""A link; formatting characters inside it are part of the address."""


def format_dt(when: datetime, style: TimestampStyle | None = None) -> str:
    """`when` as a timestamp each client shows in its reader's timezone and locale."""
    seconds = int(when.timestamp())
    return f"<t:{seconds}>" if style is None else f"<t:{seconds}:{style}>"


def _outside_links(text: str, change: "re.Pattern[str]", replace: str, *, ignore_links: bool) -> str:
    """`text` with `change` replaced by `replace`, leaving links alone when `ignore_links`."""
    if not ignore_links:
        return change.sub(replace, text)
    pieces: list[str] = []
    last = 0
    for link in _URL.finditer(text):
        pieces.append(change.sub(replace, text[last : link.start()]))
        pieces.append(link.group())
        last = link.end()
    pieces.append(change.sub(replace, text[last:]))
    return "".join(pieces)


def _escape_marker(match: "re.Match[str]") -> str:
    r"""A line's leading marker shown as typed: `\>`, `\#`, `\-`, or `1\.` for a numbered item."""
    marker = f"{match['number']}\\." if match["number"] is not None else f"\\{match['marker']}"
    return f"{match['lead']}{marker}{match['space']}"


def escape_markdown(text: str, *, ignore_links: bool = True) -> str:
    """`text` with a backslash before everything that would format it, so it shows as typed.

    Links are left as they are unless `ignore_links` is off: a backslash would break the address.
    """
    escaped = _outside_links(text, _INLINE, r"\\\g<0>", ignore_links=ignore_links)
    escaped = _LINE_START.sub(_escape_marker, escaped)
    return _MASKED_LINK.sub(lambda match: f"\\[{match['text']}\\]({match['target']})", escaped)


def remove_markdown(text: str, *, ignore_links: bool = True) -> str:
    """`text` without what would format it: the plain words, and a masked link's text and address.

    Links are left as they are unless `ignore_links` is off.
    """
    plain = _MASKED_LINK.sub(lambda match: f"{match['text']} ({match['target']})", text)
    plain = _LINE_START.sub(lambda match: match["lead"], plain)  # the marker and the space after it
    return _outside_links(plain, _INLINE, "", ignore_links=ignore_links)


def escape_mentions(text: str) -> str:
    """`text` with `@everyone`, `@here`, and user and role mentions unable to ping anyone.

    Channel mentions notify nobody and are left as they are.
    """
    return _EVERYONE.sub("@\u200b\\1", text)
