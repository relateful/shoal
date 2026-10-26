"""Cogs: classes that group commands, slash commands, event listeners and their shared state.

    class Moderation(commands.Cog, description="Keep the server tidy"):
        def __init__(self, bot: commands.Bot) -> None:
            self.bot = bot

        @commands.command()
        async def kick(self, ctx: commands.Context, member: Member) -> None: ...

        @app_commands.command()
        async def warn(self, interaction: Interaction, member: Member) -> None: ...

        @commands.Cog.listener()
        async def on_member_join(self, member: Member) -> None: ...

    await bot.add_cog(Moderation(bot))

Each cog instance gets its own copies of its commands, bound to it. `cog_load` and `cog_unload` run
when the cog is added and removed; `cog_check`, `cog_before_invoke`, `cog_after_invoke` and
`cog_command_error` apply to every prefix and hybrid command in it.
"""

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, ClassVar, Final, cast, override

from shoal.app_commands.commands import Command as AppCommandBase
from shoal.app_commands.commands import ContextMenu
from shoal.app_commands.commands import Group as AppGroup
from shoal.app_commands.parameters import NO_DESCRIPTION
from shoal.client.interaction import Interaction
from shoal.commands.core import Command, Group
from shoal.commands.hybrid import HybridCommand, HybridGroup

if TYPE_CHECKING:
    from shoal.commands.context import Context

type AppCommand = AppCommandBase | AppGroup
"""A slash command or group a cog holds."""
type Listener = Callable[..., object]

_LISTENS_TO: Final = "__shoal_cog_listener__"
"""The attribute `Cog.listener` leaves on a method: the events it listens to."""


class Cog:
    """A group of commands, slash commands and listeners; subclass it and add an instance to the bot.

    Class keywords: `name` (default: the class name) and `description` (default: the docstring).
    """

    __slots__ = ("__dict__",)

    __cog_name__: ClassVar[str] = "Cog"
    __cog_description__: ClassVar[str] = ""
    __cog_commands__: ClassVar[list[tuple[str, Command]]] = []
    __cog_app_commands__: ClassVar[list[tuple[str, AppCommand | type[AppGroup]]]] = []
    __cog_listeners__: ClassVar[list[tuple[str, str]]] = []
    """(event, method name) pairs."""

    @override
    def __init_subclass__(cls, *, name: str | None = None, description: str | None = None) -> None:
        """Collect the class's commands, slash commands and listeners, base classes first.

        Raises:
            TypeError: The class defines a context menu, which cannot be a method.
        """
        super().__init_subclass__()
        cls.__cog_name__ = name or cls.__name__
        cls.__cog_description__ = description if description is not None else (cls.__doc__ or "").strip()
        commands: dict[str, Command] = {}
        app_commands: dict[str, AppCommand | type[AppGroup]] = {}
        listeners: dict[str, list[str]] = {}
        for base in reversed(cls.__mro__):
            for attribute, value in vars(base).items():
                member: object = value
                if isinstance(member, ContextMenu):
                    msg = f"{cls.__name__}.{attribute}: add context menus to the tree, not to a cog"
                    raise TypeError(msg)
                if isinstance(member, Command):
                    commands[attribute] = member
                elif (isinstance(member, AppCommandBase | AppGroup) and member.parent is None) or (
                    isinstance(member, type) and issubclass(member, AppGroup)
                ):
                    # A subcommand made with `@group.command()` belongs to its group.
                    app_commands[attribute] = member
                events: object = getattr(value, _LISTENS_TO, None)
                if isinstance(events, tuple):
                    # isinstance narrows to tuple[Unknown, ...]
                    listeners[attribute] = [str(event) for event in cast("tuple[object, ...]", events)]
        # A subcommand belongs to its group, not to the cog directly.
        cls.__cog_commands__ = [(key, command) for key, command in commands.items() if command.parent is None]
        cls.__cog_app_commands__ = list(app_commands.items())
        cls.__cog_listeners__ = [
            (event, attribute) for attribute, events in listeners.items() for event in events
        ]

    @classmethod
    def listener[F: Listener](cls, name: str | None = None) -> Callable[[F], F]:
        """Mark a method as a listener for event `name` (default: the method's name without `on_`).

        Raises:
            TypeError: The function's name does not say its event and no `name` was given.
        """

        def decorator(function: F) -> F:
            event: str = name or str(getattr(function, "__name__", ""))
            if not name and not event.startswith("on_"):
                msg = f"{event} must be named after its event, such as on_message, or be given a name"
                raise TypeError(msg)
            events: object = getattr(function, _LISTENS_TO, ())
            # Only this decorator sets the attribute, always to a tuple of event names.
            known = cast("tuple[str, ...]", events) if isinstance(events, tuple) else ()
            setattr(function, _LISTENS_TO, (*known, event.removeprefix("on_")))
            return function

        return decorator

    @property
    def qualified_name(self) -> str:
        """The cog's name."""
        return self.__cog_name__

    @property
    def description(self) -> str:
        """The cog's description."""
        return self.__cog_description__

    def get_commands(self) -> list[Command]:
        """The cog's top-level prefix and hybrid commands (this instance's copies once it is added)."""
        return [getattr(self, attribute) for attribute, _ in self.__cog_commands__]

    def walk_commands(self) -> Iterator[Command]:
        """Every prefix and hybrid command, subcommands included."""
        for command in self.get_commands():
            yield command
            if isinstance(command, Group):
                yield from command.walk_commands()

    def get_app_commands(self) -> list[AppCommand]:
        """The cog's slash commands and groups (this instance's copies once it is added)."""
        return [getattr(self, attribute) for attribute, _ in self.__cog_app_commands__]

    def get_listeners(self) -> list[tuple[str, Callable[..., object]]]:
        """The cog's listeners: (event, bound method) pairs."""
        return [(event, getattr(self, attribute)) for event, attribute in self.__cog_listeners__]

    def bind(self) -> None:
        """Give this instance its own copies of the class's commands, bound to it (the bot does this)."""
        for attribute, command in self.__cog_commands__:
            setattr(self, attribute, command.bound(self))
        for attribute, app_command in self.__cog_app_commands__:
            if isinstance(app_command, type):
                setattr(self, attribute, app_command())
            else:
                setattr(self, attribute, app_command.bound(self))

    async def cog_load(self) -> None:
        """Runs when the cog is added to the bot; override it to set up."""

    async def cog_unload(self) -> None:
        """Runs when the cog is removed from the bot; override it to clean up."""

    def cog_check(self, ctx: "Context") -> bool:
        """A check for every prefix and hybrid command in the cog; the default allows them."""
        del ctx
        return True

    async def cog_command_error(self, ctx: "Context", error: Exception) -> None:
        """Handles errors from the cog's prefix and hybrid commands; the default does nothing."""
        del ctx, error

    async def cog_before_invoke(self, ctx: "Context") -> None:
        """Runs before each of the cog's prefix and hybrid commands."""
        del ctx

    async def cog_after_invoke(self, ctx: "Context") -> None:
        """Runs after each of the cog's prefix and hybrid commands."""
        del ctx

    async def interaction_check(self, interaction: Interaction) -> bool:
        """A check for every slash command in the cog; the default allows them."""
        del interaction
        return True

    async def cog_app_command_error(self, interaction: Interaction, error: Exception) -> None:
        """Handles errors from the cog's slash commands; the default does nothing."""
        del interaction, error

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.qualified_name!r}>"


class GroupCog(Cog):
    """A cog whose slash commands (and hybrid commands' slash sides) are one slash group's subcommands.

        class Tags(commands.GroupCog, group_name="tags", group_description="Saved answers"):
            @app_commands.command()
            async def show(self, interaction: Interaction, name: str) -> None: ...  # /tags show

    Class keywords as for `Cog`, and `group_name` (default: the cog's name, lowercased, spaces as
    dashes), `group_description` (default: the cog's description) and `group_nsfw`.
    """

    __slots__ = ()

    __cog_group_name__: ClassVar[str] = "cog"
    __cog_group_description__: ClassVar[str] = NO_DESCRIPTION
    __cog_group_nsfw__: ClassVar[bool] = False

    _group: AppGroup | None = None

    @override
    def __init_subclass__(
        cls,
        *,
        name: str | None = None,
        description: str | None = None,
        group_name: str | None = None,
        group_description: str | None = None,
        group_nsfw: bool = False,
    ) -> None:
        """Collect the class's commands as `Cog` does, and remember the slash group's details."""
        super().__init_subclass__(name=name, description=description)
        cls.__cog_group_name__ = group_name or cls.__cog_name__.lower().replace(" ", "-")
        cls.__cog_group_description__ = group_description or cls.__cog_description__ or NO_DESCRIPTION
        cls.__cog_group_nsfw__ = group_nsfw

    @override
    def bind(self) -> None:
        """Bind the commands as `Cog` does, then gather the slash ones in the cog's slash group."""
        super().bind()
        group = AppGroup(name=self.__cog_group_name__, description=self.__cog_group_description__)
        group.nsfw = self.__cog_group_nsfw__
        for app_command in super().get_app_commands():
            group.add_command(app_command)
        for command in self.get_commands():
            if isinstance(command, HybridCommand | HybridGroup):
                group.add_command(command.app_command)
        self._group = group

    @property
    def app_command(self) -> AppGroup:
        """The cog's slash group.

        Raises:
            RuntimeError: The cog is not added to a bot yet; the group is made then.
        """
        if self._group is None:
            msg = f"{type(self).__name__} has no slash group until it is added to a bot"
            raise RuntimeError(msg)
        return self._group

    @override
    def get_app_commands(self) -> list[AppCommand]:
        """The cog's slash group, holding its slash commands."""
        return [self.app_command]
