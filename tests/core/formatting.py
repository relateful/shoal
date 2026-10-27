from datetime import UTC, datetime

import pytest

from shoal.core.formatting import (
    ANY_MENTION,
    TIMESTAMP,
    escape_markdown,
    escape_mentions,
    format_dt,
    remove_markdown,
)

USER = "123456789012345678"


def test_timestamps_format_and_parse_back() -> None:
    when = datetime(2021, 4, 20, 21, 20, 30, tzinfo=UTC)
    assert format_dt(when) == "<t:1618953630>"
    assert format_dt(when, "R") == "<t:1618953630:R>"
    match = TIMESTAMP.fullmatch(format_dt(when, "F"))
    assert match is not None
    assert match.groups() == ("1618953630", "F")


@pytest.mark.parametrize(
    ("text", "escaped"),
    [
        ("**bold** _x_ ~~s~~ `c` ||spoiler||", r"\*\*bold\*\* \_x\_ \~\~s\~\~ \`c\` \|\|spoiler\|\|"),
        ("> quote\n>>> block\n# heading\n-# subtext", "\\> quote\n\\>>> block\n\\# heading\n\\-# subtext"),
        ("- item\n  * nested\n12. twelfth", "\\- item\n  \\* nested\n12\\. twelfth"),
        ("[docs](https://e.com)", r"\[docs\](https://e.com)"),
        ("a\\b", r"a\\b"),
        ("see https://e.com/a_b_c", "see https://e.com/a_b_c"),
        ("#hashtag and 5.5 and -1", "#hashtag and 5.5 and -1"),
    ],
)
def test_markdown_is_escaped_to_show_as_typed(text: str, escaped: str) -> None:
    assert escape_markdown(text) == escaped


def test_links_are_escaped_too_when_asked() -> None:
    assert escape_markdown("https://e.com/a_b", ignore_links=False) == r"https://e.com/a\_b"
    assert remove_markdown("https://e.com/a_b", ignore_links=False) == "https://e.com/ab"


@pytest.mark.parametrize(
    ("text", "plain"),
    [
        ("**bold** _x_ ~~s~~ `c`", "bold x s c"),
        ("> quote\n## heading\n- item\n12. twelfth", "quote\nheading\nitem\ntwelfth"),
        ("[docs](https://e.com)", "docs (https://e.com)"),
        ("keep https://e.com/a_b", "keep https://e.com/a_b"),
    ],
)
def test_markdown_can_be_removed(text: str, plain: str) -> None:
    assert remove_markdown(text) == plain


def test_mentions_are_made_unable_to_ping() -> None:
    text = f"@everyone @here <@{USER}> <@!{USER}> <@&{USER}> <#{USER}>"
    escaped = escape_mentions(text)
    assert escaped == (
        f"@\u200beveryone @\u200bhere <@\u200b{USER}> <@\u200b!{USER}> <@\u200b&{USER}> <#{USER}>"
    )
    assert ANY_MENTION.search(escaped.replace(f"<#{USER}>", "")) is None
