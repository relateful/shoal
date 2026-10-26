"""The application's emojis by name, loaded when the client logs in, reachable wherever the client is.

    emojis = interaction.client.app_emojis
    await interaction.response.send_message(f"{emojis.approve} Saved")
    await message.add_reaction(emojis.star)
    button = ui.Button(label="Settings", emoji=emojis.settings)

Attribute access (`emojis.approve`, the same as `emojis.resolve("approve")`) gives the emoji, or
its unicode fallback while it is not uploaded (a fresh application, or tests); either works in a
message, a reaction or a component. A name with neither raises, rather than showing nothing where
the icon should be. Names that clash with the registry's own methods use `resolve`.

Declare the names a bot uses, with their fallbacks, by subclassing; the type checker then knows
each one, and the client warns at login about any not uploaded:

    class Icons(AppEmojis):
        approve = app_emoji("✅")
        star = app_emoji("⭐")

    client = Client(intents=intents, app_emojis=Icons())

Discord: https://docs.discord.com/developers/resources/emoji#emoji-object-applicationowned-emoji
"""

import logging
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import ClassVar, Self, overload, override

from shoal.core.errors import ShoalError
from shoal.core.snowflake import Snowflake
from shoal.emojis.sync import SyncReport, sync_emojis
from shoal.models.emoji import AppEmoji
from shoal.models.state import State
from shoal.payloads.emoji import CreateApplicationEmojiParams, emoji_data

_log = logging.getLogger("shoal.emojis")


class EmojisNotLoadedError(ShoalError):
    """The registry was used for something that needs the application before the client logged in."""

    def __init__(self) -> None:
        """The error for a registry not loaded yet."""
        super().__init__("the application's emojis load when the client logs in")


class DeclaredEmoji:
    """An application emoji a registry subclass declares; reading it gives the emoji or its fallback."""

    __slots__ = ("fallback", "name")

    def __init__(self, fallback: str | None) -> None:
        """A declared emoji shown as `fallback` while not uploaded."""
        self.fallback: str | None = fallback
        self.name: str = ""

    def __set_name__(self, owner: type, name: str) -> None:
        """Take the attribute's name as the emoji's."""
        self.name = name

    @overload
    def __get__(self, instance: None, owner: type) -> Self: ...
    @overload
    def __get__(self, instance: "AppEmojis", owner: type) -> AppEmoji | str: ...
    def __get__(self, instance: "AppEmojis | None", owner: type) -> "Self | AppEmoji | str":
        """The emoji (or its fallback) on an instance; the declaration itself on the class."""
        return self if instance is None else instance.resolve(self.name)


def app_emoji(fallback: str | None = None) -> DeclaredEmoji:
    """Declare an application emoji on an `AppEmojis` subclass, shown as `fallback` until uploaded."""
    return DeclaredEmoji(fallback)


class AppEmojis:
    """The application's emojis by name, with unicode fallbacks for names not uploaded.

    Discord: https://docs.discord.com/developers/resources/emoji#list-application-emojis
    """

    __slots__ = ("_application_id", "_by_name", "_fallen_back", "_state", "fallbacks")

    declared: ClassVar[dict[str, DeclaredEmoji]] = {}
    """The emojis the class declares with `app_emoji`, by name."""

    @override
    def __init_subclass__(cls) -> None:
        """Collect the emojis the class declares, base classes first.

        Raises:
            TypeError: A declared name is one of the registry's own attributes (`get`, `sync`, ...),
                which it would hide; use `resolve` for an emoji with such a name.
        """
        super().__init_subclass__()
        clashing = sorted(
            name
            for name, member in vars(cls).items()
            if isinstance(member, DeclaredEmoji) and hasattr(AppEmojis, name)
        )
        if clashing:
            names = ", ".join(clashing)
            msg = f"{cls.__name__} declares {names}, which the registry uses; read them with resolve()"
            raise TypeError(msg)
        cls.declared = {
            name: member
            for base in reversed(cls.__mro__)
            for name, member in vars(base).items()
            if isinstance(member, DeclaredEmoji)
        }

    def __init__(self, fallbacks: Mapping[str, str] | None = None) -> None:
        """An empty registry; `fallbacks` adds unicode shown for names not uploaded yet."""
        declared = {name: item.fallback for name, item in self.declared.items() if item.fallback is not None}
        self.fallbacks: dict[str, str] = declared | dict(fallbacks or {})
        self._by_name: dict[str, AppEmoji] = {}
        self._fallen_back: set[str] = set()
        self._state: State | None = None
        self._application_id: Snowflake | None = None

    async def load(self, state: State, application_id: int) -> None:
        """Fetch application `application_id`'s emojis; the client does this when it logs in."""
        self._state = state
        self._application_id = Snowflake(application_id)
        await self.refresh()

    async def refresh(self) -> None:
        """Fetch the emojis again, after they changed outside this process.

        Raises:
            EmojisNotLoadedError: The client has not logged in.
        """
        state, application_id = self._bound()
        listed = await state.rest.emojis.list_for_application(application_id)
        emojis = [
            AppEmoji(state, data, application_id) for data in listed if data.id is not None and data.name
        ]
        self._by_name = {emoji.name: emoji for emoji in emojis}
        self._fallen_back.clear()
        missing = self.missing
        if missing:
            _log.warning("declared application emojis not uploaded: %s", ", ".join(missing))

    @property
    def missing(self) -> list[str]:
        """The declared emojis the application does not have, by name."""
        return sorted(name for name in self.declared if name not in self._by_name)

    def get(self, name: str, /) -> AppEmoji | None:
        """The emoji called `name`, if the application has one."""
        return self._by_name.get(name)

    def resolve(self, name: str, /) -> AppEmoji | str:
        """The emoji called `name`, or its unicode fallback: what messages, reactions and components take.

        Raises:
            KeyError: The application has no such emoji and the name has no fallback.
        """
        emoji = self._by_name.get(name)
        if emoji is not None:
            return emoji
        fallback = self.fallbacks.get(name)
        if fallback is None:
            msg = f"the application has no emoji named {name!r}; upload it, or give it a fallback"
            raise KeyError(msg)
        if name not in self._fallen_back:
            self._fallen_back.add(name)
            _log.warning("application emoji %r is not uploaded; showing %s instead", name, fallback)
        return fallback

    def text(self, name: str, /) -> str:
        """The text that shows emoji `name` in a message: `<:name:id>`, or its fallback.

        Raises:
            KeyError: The application has no such emoji and the name has no fallback.
        """
        return str(self.resolve(name))

    async def create(self, name: str, image: bytes) -> AppEmoji:
        """Upload an emoji (JPEG, PNG, GIF, WebP or AVIF, at most 256 KiB) and add it here.

        Raises:
            EmojisNotLoadedError: The client has not logged in.
            ValueError: The image is too large or not one of those formats.

        Discord: https://docs.discord.com/developers/resources/emoji#create-application-emoji
        """
        state, application_id = self._bound()
        params = CreateApplicationEmojiParams(name=name, image=emoji_data(image))
        emoji = AppEmoji(
            state, await state.rest.emojis.create_for_application(application_id, params), application_id
        )
        self._by_name[emoji.name] = emoji
        return emoji

    async def delete(self, name: str, /) -> None:
        """Delete the emoji called `name`.

        Raises:
            EmojisNotLoadedError: The client has not logged in.
            KeyError: The application has no such emoji.

        Discord: https://docs.discord.com/developers/resources/emoji#delete-application-emoji
        """
        emoji = self._by_name.get(name)
        if emoji is None:
            msg = f"the application has no emoji named {name!r}"
            raise KeyError(msg)
        await emoji.delete()
        del self._by_name[name]

    async def sync(
        self, folder: Path, *, prune: bool = False, replace_unknown: bool = False, dry_run: bool = False
    ) -> SyncReport:
        """Make the application's emojis match a folder of images, then fetch them again.

        See `sync_emojis` for how the folder and its manifest are used.

        Raises:
            EmojisNotLoadedError: The client has not logged in.
            NotADirectoryError: `folder` is not a directory.
        """
        state, application_id = self._bound()
        report = await sync_emojis(
            state.rest, application_id, folder, prune=prune, replace_unknown=replace_unknown, dry_run=dry_run
        )
        if not dry_run:
            await self.refresh()
        return report

    def _bound(self) -> tuple[State, Snowflake]:
        if self._state is None or self._application_id is None:
            raise EmojisNotLoadedError
        return self._state, self._application_id

    def __getattr__(self, name: str) -> AppEmoji | str:
        """`emojis.approve`: the emoji called `name`, or its fallback (see `resolve`).

        Raises:
            AttributeError: The application has no such emoji and the name has no fallback.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self.resolve(name)
        except KeyError as error:
            raise AttributeError(*error.args) from None

    def __getitem__(self, name: str, /) -> AppEmoji:
        """The emoji called `name`.

        Raises:
            KeyError: The application has no such emoji.
        """
        emoji = self._by_name.get(name)
        if emoji is None:
            msg = f"the application has no emoji named {name!r}"
            raise KeyError(msg)
        return emoji

    def __contains__(self, name: object, /) -> bool:
        """Whether the application has an emoji called `name`."""
        return name in self._by_name

    def __iter__(self) -> Iterator[AppEmoji]:
        """The emojis, by name."""
        return iter(sorted(self._by_name.values(), key=lambda emoji: emoji.name))

    def __len__(self) -> int:
        """How many emojis the application has."""
        return len(self._by_name)
