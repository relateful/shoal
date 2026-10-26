import pytest

from shoal.commands.errors import (
    ExpectedClosingQuoteError,
    InvalidEndOfQuotedStringError,
    UnexpectedQuoteError,
)
from shoal.commands.view import StringView


def words(text: str) -> list[str]:
    view = StringView(text)
    found: list[str] = []
    while True:
        view.skip_ws()
        word = view.get_quoted_word()
        if word is None:
            return found
        found.append(word)


def test_words_split_on_whitespace_and_quotes_group_them() -> None:
    assert words('tag create "hello world"  body') == ["tag", "create", "hello world", "body"]
    assert words("“curly quotes” and «guillemets»") == ["curly quotes", "and", "guillemets"]
    assert words("") == []


def test_quotes_can_be_escaped_inside_quoted_text() -> None:
    assert words('"say \\"hi\\"" \\x') == ['say "hi"', "\\x"]
    assert words('"back\\\\slash"') == ["back\\slash"]


def test_misplaced_quotes_are_refused() -> None:
    with pytest.raises(UnexpectedQuoteError):
        words('ab"c')
    with pytest.raises(InvalidEndOfQuotedStringError):
        words('"ab"c')
    with pytest.raises(ExpectedClosingQuoteError, match="”"):
        words("“never closed")


def test_the_view_moves_back_and_reads_the_rest() -> None:
    view = StringView("!ping  rest of it")
    assert view.skip_string("!")
    assert not view.skip_string("?")
    assert view.get_word() == "ping"
    view.undo()
    assert view.get_word() == "ping"
    assert view.skip_ws()
    assert not view.skip_ws()
    assert view.read_rest() == "rest of it"
    assert view.eof
    assert view.get_quoted_word() is None
