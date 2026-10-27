"""Translating commands: names, descriptions and choices in each of Discord's languages.

    class Strings(app_commands.Translator):
        async def translate(self, string, locale, context) -> str | None:
            return CATALOG.get(locale, {}).get(string.message)

    await tree.set_translator(Strings())
    await tree.sync()  # each name and description is sent with its translations

The translator is asked about every command, group, option and choice name and description, in
every locale; returning `None` leaves that one untranslated.

Discord: https://docs.discord.com/developers/interactions/application-commands#localization
"""

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from shoal.app_commands.errors import AppCommandError
from shoal.payloads.api import Locale, Localizations

if TYPE_CHECKING:
    from shoal.app_commands.commands import Command, ContextMenu, Group
    from shoal.app_commands.models import AnyChoice
    from shoal.app_commands.parameters import Parameter


class locale_str:  # noqa: N801 - the name every bot writes, as `str` is
    """A string to translate, with `extras` the translator may use (a key, a plural count).

    It reads as its message: `str(locale_str("hello"))` is `"hello"`.
    """

    __slots__ = ("extras", "message")

    def __init__(self, message: str, /, **extras: object) -> None:
        """The text `message`, and anything else the translator should know."""
        self.message: str = message
        self.extras: dict[str, object] = extras

    @override
    def __str__(self) -> str:
        return self.message

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, locale_str) and other.message == self.message

    @override
    def __hash__(self) -> int:
        return hash(self.message)

    @override
    def __repr__(self) -> str:
        return f"locale_str({self.message!r})"


class TranslationContextLocation(enum.Enum):
    """What a string being translated is."""

    COMMAND_NAME = enum.auto()
    COMMAND_DESCRIPTION = enum.auto()
    GROUP_NAME = enum.auto()
    GROUP_DESCRIPTION = enum.auto()
    PARAMETER_NAME = enum.auto()
    PARAMETER_DESCRIPTION = enum.auto()
    CHOICE_NAME = enum.auto()


type TranslationContextData = "Command | Group | ContextMenu | Parameter | AnyChoice"
"""What a translated string belongs to."""


@dataclass(frozen=True, slots=True)
class TranslationContext:
    """Where a string being translated comes from: `location` says what it is, `data` whose it is."""

    location: TranslationContextLocation
    data: TranslationContextData


class TranslationError(AppCommandError):
    """A translator raised while translating."""

    def __init__(self, string: locale_str, locale: Locale, original: Exception) -> None:
        """Translating `string` into `locale` raised `original`."""
        super().__init__(f"translating {string.message!r} into {locale.value} failed: {original}")
        self.string: locale_str = string
        self.locale: Locale = locale
        self.original: Exception = original


class Translator:
    """Translates the tree's commands; override `translate` (and `load` and `unload` if needed)."""

    __slots__ = ()

    async def load(self) -> None:
        """Runs when the translator is set on a tree: read the catalog here."""

    async def unload(self) -> None:
        """Runs when the tree stops using the translator."""

    async def translate(self, string: locale_str, locale: Locale, context: TranslationContext) -> str | None:
        """`string` in `locale`, or `None` to leave it untranslated; the default translates nothing."""
        del string, locale, context
        return None

    async def localizations(self, text: str, context: TranslationContext) -> Localizations:
        """`text` in every locale the translator knows.

        Raises:
            TranslationError: `translate` raised.
        """
        string = locale_str(text)
        found: Localizations = {}
        for locale in Locale:
            try:
                translated = await self.translate(string, locale, context)
            except Exception as error:
                raise TranslationError(string, locale, error) from error
            if translated is not None:
                found[locale] = translated
        return found
