"""Splitting a command's text into arguments: words, or quoted text with escapes.

    !tag create "hello world" body   ->   tag, create, hello world, body

Opening quotes pair with their own closing quote, including the curly and CJK quotes phone
keyboards insert. Inside quotes a backslash escapes the quote; outside, a quote may not appear in
the middle of a word.
"""

from typing import Final

from shoal.commands.errors import (
    ExpectedClosingQuoteError,
    InvalidEndOfQuotedStringError,
    UnexpectedQuoteError,
)

QUOTES: Final[dict[str, str]] = {
    '"': '"',
    "\u2018": "\u2019",
    "\u201a": "\u201b",
    "\u201c": "\u201d",
    "\u201e": "\u201f",
    "\u2e42": "\u2e42",
    "\u300c": "\u300d",
    "\u300e": "\u300f",
    "\u301d": "\u301e",
    "\ufe41": "\ufe42",
    "\ufe43": "\ufe44",
    "\uff02": "\uff02",
    "\uff62": "\uff63",
    "\u00ab": "\u00bb",
    "\u2039": "\u203a",
    "\u300a": "\u300b",
    "\u3008": "\u3009",
}
"""Each opening quote and the quote that closes it."""
_ALL_QUOTES: Final = frozenset(QUOTES) | frozenset(QUOTES.values())


class StringView:
    """A cursor over a command's text, read one argument at a time."""

    __slots__ = ("buffer", "index", "previous")

    def __init__(self, buffer: str) -> None:
        """A view at the start of `buffer`."""
        self.buffer: str = buffer
        self.index: int = 0
        self.previous: int = 0

    @property
    def eof(self) -> bool:
        """Whether everything has been read."""
        return self.at_end()

    def at_end(self) -> bool:
        """Whether everything has been read; a method, so checkers never assume it stays the same."""
        return self.index >= len(self.buffer)

    def undo(self) -> None:
        """Go back to before the last read."""
        self.index = self.previous

    def skip_ws(self) -> bool:
        """Skip whitespace; whether there was any."""
        start = self.index
        while not self.at_end() and self.buffer[self.index].isspace():
            self.index += 1
        return self.index != start

    def skip_string(self, text: str) -> bool:
        """Skip `text` if the view is at it; whether it was."""
        if self.buffer.startswith(text, self.index):
            self.previous = self.index
            self.index += len(text)
            return True
        return False

    def read_rest(self) -> str:
        """Everything not yet read."""
        self.previous = self.index
        rest = self.buffer[self.index :]
        self.index = len(self.buffer)
        return rest

    def get_word(self) -> str:
        """The text up to the next whitespace, quotes and all."""
        self.previous = self.index
        start = self.index
        while not self.at_end() and not self.buffer[self.index].isspace():
            self.index += 1
        return self.buffer[start : self.index]

    def get_quoted_word(self) -> str | None:
        """The next argument: a quoted string (without its quotes) or a word; `None` at the end.

        Raises:
            ExpectedClosingQuoteError: A quote is never closed.
            InvalidEndOfQuotedStringError: A closing quote is followed by something other than space.
            UnexpectedQuoteError: A quote appears in the middle of an unquoted word.
        """
        self.previous = self.index
        if self.at_end():
            return None
        opening = self.buffer[self.index]
        closing = QUOTES.get(opening)
        if closing is not None:
            self.index += 1
        result: list[str] = []
        while not self.at_end():
            current = self.buffer[self.index]
            self.index += 1
            if closing is None:
                if current.isspace():
                    self.index -= 1
                    return "".join(result)
                if current in _ALL_QUOTES:
                    raise UnexpectedQuoteError(current)
                result.append(current)
                continue
            if current == "\\" and not self.at_end() and self.buffer[self.index] in {closing, "\\"}:
                result.append(self.buffer[self.index])
                self.index += 1
                continue
            if current == closing:
                if not self.at_end() and not self.buffer[self.index].isspace():
                    raise InvalidEndOfQuotedStringError(self.buffer[self.index])
                return "".join(result)
            result.append(current)
        if closing is not None:
            raise ExpectedClosingQuoteError(closing)
        return "".join(result)
