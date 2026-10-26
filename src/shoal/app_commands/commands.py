"""Slash commands, groups of them, and context menu commands.

    @tree.command(description="Ban a member")
    @app_commands.describe(member="Who to ban", days="How many days of messages to delete")
    @app_commands.default_permissions(ban_members=True)
    async def ban(interaction: Interaction, member: Member, days: Range[int, 0, 7] = 1) -> None: ...

    class Tags(app_commands.Group, description="Server tags"):
        @app_commands.command(description="Show a tag")
        async def show(self, interaction: Interaction, name: str) -> None: ...

    tree.add_command(Tags())

Discord: https://docs.discord.com/developers/interactions/application-commands
"""

import dataclasses
import inspect
import re
import types
import typing
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import ClassVar, Final, Self, cast, override

from msgspec import UNSET, UnsetType

from shoal.app_commands.errors import CheckFailureError, NoPrivateMessageError, TransformerError
from shoal.app_commands.models import AnyChoice
from shoal.app_commands.parameters import REQUIRED, AutocompleteCallback, Parameter, parameter_from_annotation
from shoal.client.interaction import Interaction
from shoal.models.member import Member
from shoal.models.message import Message
from shoal.models.user import User
from shoal.payloads.application import ApplicationIntegrationType, InteractionContextType
from shoal.payloads.application_commands import (
    COMMAND_DESCRIPTION_MAX_LENGTH,
    COMMAND_MAX_OPTIONS,
    COMMAND_NAME_MAX_LENGTH,
    OPTION_MAX_CHOICES,
    ApplicationCommandOption,
    ApplicationCommandOptionType,
    ApplicationCommandType,
    OverwriteCommandParams,
)
from shoal.payloads.interactions import ApplicationCommandInteractionDataOption, ResolvedData
from shoal.payloads.permissions import Permissions

type Check = Callable[[Interaction], bool | Awaitable[bool]]
"""A predicate run before the command: return `False` (or raise `CheckFailureError`) to refuse."""
type ErrorHandler = Callable[[Interaction, Exception], Awaitable[None]]
"""Handles an error a command raised."""
type CommandCallback = Callable[..., Awaitable[None]]
"""`async def name(interaction, ...)`, or `async def name(self, interaction, ...)` in a group."""
type ContextMenuCallback = Callable[..., Awaitable[None]]
"""`async def name(interaction, member: Member)` or `async def name(interaction, message: Message)`."""
type Suggester = Callable[..., Awaitable[Sequence[AnyChoice]]]
"""An autocomplete callback: `(interaction, current)`, or `(self, interaction, current)` in a group."""

NO_DESCRIPTION: Final = "…"
"""The description of a command or option that has none."""
_NAME: Final = re.compile(rf"^[-_'\w]{{1,{COMMAND_NAME_MAX_LENGTH}}}$")
"""What Discord accepts as a command or option name (ignoring the scripts it adds to `\\w`).

Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-object-application-command-naming
"""
_PENDING: Final = "__shoal_app_command__"
"""The attribute decorators below `@command` leave on the function, read when the command is made."""
_ARGS_HEADINGS: Final = frozenset({"Args:", "Arguments:", "Parameters:"})


@dataclass(slots=True)
class _Pending:
    """Settings decorators record on a function before it becomes a command."""

    descriptions: dict[str, str] = field(default_factory=dict[str, str])
    renames: dict[str, str] = field(default_factory=dict[str, str])
    choices: dict[str, list[AnyChoice]] = field(default_factory=dict[str, list[AnyChoice]])
    autocompletes: dict[str, AutocompleteCallback] = field(default_factory=dict[str, AutocompleteCallback])
    checks: list[Check] = field(default_factory=list[Check])
    guild_only: bool = False
    nsfw: bool = False
    default_permissions: Permissions | None = None
    guild_ids: list[int] = field(default_factory=list[int])
    contexts: list[InteractionContextType] | None = None
    installs: list[ApplicationIntegrationType] | None = None


def _pending(function: object) -> _Pending:
    found = getattr(function, _PENDING, None)
    if isinstance(found, _Pending):
        return found
    created = _Pending()
    setattr(function, _PENDING, created)
    return created


def _check_name(name: str) -> str:
    if not _NAME.match(name) or name != name.lower():
        msg = (
            f"{name!r} is not a valid command or option name: 1 to {COMMAND_NAME_MAX_LENGTH} lowercase "
            "letters, digits, - and _"
        )
        raise ValueError(msg)
    return name


def _check_description(text: str, of: str) -> str:
    if not 1 <= len(text) <= COMMAND_DESCRIPTION_MAX_LENGTH:
        limit = COMMAND_DESCRIPTION_MAX_LENGTH
        msg = f"the description of {of!r} has {len(text)} characters; Discord takes 1 to {limit}"
        raise ValueError(msg)
    return text


def _check_choices(listed: Sequence[AnyChoice], of: str) -> list[AnyChoice]:
    if len(listed) > OPTION_MAX_CHOICES:
        msg = f"option {of!r} has {len(listed)} choices; Discord takes at most {OPTION_MAX_CHOICES}"
        raise ValueError(msg)
    for choice in listed:
        if not 1 <= len(choice.name) <= COMMAND_DESCRIPTION_MAX_LENGTH:
            limit = COMMAND_DESCRIPTION_MAX_LENGTH
            msg = f"choice {choice.name!r} of {of!r} needs a name of 1 to {limit} characters"
            raise ValueError(msg)
    return list(listed)


def _docstring(doc: str | None) -> tuple[str | None, dict[str, str]]:
    """The first line of a docstring, and its Google-style `Args:` entries (continuations joined)."""
    if not doc:
        return None, {}
    lines = inspect.cleandoc(doc).splitlines()
    described: dict[str, str] = {}
    current: str | None = None
    in_args = False
    for line in lines[1:]:
        stripped = line.strip()
        if stripped in _ARGS_HEADINGS:
            in_args, current = True, None
        elif not line.startswith(" "):
            # A blank line inside `Args:` keeps it open; any other unindented line ends it.
            in_args = in_args and not stripped
            current = None
        elif in_args and current is not None and line.startswith(" " * 8):
            described[current] = f"{described[current]} {stripped}"
        elif in_args:
            name, _, text = stripped.partition(":")
            current = name.split(" ")[0]
            described[current] = text.strip()
    return lines[0].strip() or None, described


class _CommandBase:
    """What commands, groups and context menus share: permissions, contexts and checks."""

    __slots__ = (
        "_error_handler",
        "allowed_contexts",
        "allowed_installs",
        "checks",
        "default_permissions",
        "extras",
        "guild_ids",
        "guild_only",
        "name",
        "nsfw",
    )

    def __init__(self, name: str, pending: _Pending, extras: Mapping[str, object] | None) -> None:
        self.name: str = name
        self.checks: list[Check] = list(pending.checks)
        self.guild_only: bool = pending.guild_only
        self.nsfw: bool = pending.nsfw
        self.default_permissions: Permissions | None = pending.default_permissions
        self.guild_ids: list[int] = list(pending.guild_ids)
        self.allowed_contexts: list[InteractionContextType] | None = pending.contexts
        self.allowed_installs: list[ApplicationIntegrationType] | None = pending.installs
        self.extras: dict[str, object] = dict(extras or {})
        self._error_handler: ErrorHandler | None = None

    def add_check(self, predicate: Check) -> None:
        """Run `predicate` before the command."""
        self.checks.append(predicate)

    def error[F: ErrorHandler](self, handler: F) -> F:
        """Handle errors this command (or group) raises; the tree's handler still runs after it."""
        self._error_handler = handler
        return handler

    @property
    def error_handler(self) -> ErrorHandler | None:
        """The handler set with `error`."""
        return self._error_handler

    def _payload(self, kind: ApplicationCommandType) -> OverwriteCommandParams:
        """The fields every kind of command sends; slash commands add a description and options."""
        return OverwriteCommandParams(
            name=self.name,
            type=kind,
            default_member_permissions=UNSET
            if self.default_permissions is None
            else self.default_permissions,
            contexts=self._contexts(),
            integration_types=UNSET if self.allowed_installs is None else list(self.allowed_installs),
            nsfw=True if self.nsfw else UNSET,
        )

    def _contexts(self) -> list[InteractionContextType] | UnsetType:
        if self.allowed_contexts is not None:
            return list(self.allowed_contexts)
        return [InteractionContextType.GUILD] if self.guild_only else UNSET

    async def run_checks(self, interaction: Interaction) -> None:
        """Run the command's checks.

        Raises:
            CheckFailureError: A check refused, or the command is guild-only and used elsewhere.
        """
        if self.guild_only and interaction.guild_id is None:
            raise NoPrivateMessageError
        for predicate in self.checks:
            result = predicate(interaction)
            passed = await result if inspect.isawaitable(result) else result
            if not passed:
                msg = f"a check of {self.name!r} refused the interaction"
                raise CheckFailureError(msg)


class Command(_CommandBase):
    """A slash command, or a subcommand in a group.

    Discord: https://docs.discord.com/developers/interactions/application-commands#slash-commands
    """

    __slots__ = ("binding", "callback", "description", "parameters", "parent")

    def __init__(
        self,
        *,
        callback: CommandCallback,
        name: str | None = None,
        description: str | None = None,
        nsfw: bool = False,
        extras: Mapping[str, object] | None = None,
    ) -> None:
        """A command running `callback`; its name and description default to the function's.

        Raises:
            TypeError: The callback is not a coroutine function, or a parameter has no usable hint.
            ValueError: A name, description or choice is not one Discord accepts, or there are more
                than 25 options.
        """
        if not inspect.iscoroutinefunction(callback):
            msg = f"the callback of a command must be async: {callback!r}"
            raise TypeError(msg)
        pending = _pending(callback)
        super().__init__(_check_name(name or callback.__name__), pending, extras)
        summary, described = _docstring(callback.__doc__)
        self.callback: CommandCallback = callback
        self.description: str = _check_description(description or summary or NO_DESCRIPTION, self.name)
        self.nsfw = self.nsfw or nsfw
        self.parent: Group | None = None
        self.binding: object | None = None
        self.parameters: list[Parameter] = _parameters(callback, pending, described)

    @property
    def qualified_name(self) -> str:
        """The command's full name, with its groups: `tags show`."""
        return f"{self.parent.qualified_name} {self.name}" if self.parent is not None else self.name

    def get_parameter(self, name: str) -> Parameter | None:
        """The parameter called `name` (the Python name, or the option's name)."""
        return next((item for item in self.parameters if name in {item.name, item.display_name}), None)

    def autocomplete[F: Suggester](self, name: str) -> Callable[[F], F]:
        """Suggest choices for option `name` as the user types: `async def(interaction, current)`.

        Raises:
            KeyError: The command has no such option.
        """
        parameter = _require(self, name)

        def decorator(function: F) -> F:
            parameter.autocomplete = cast("AutocompleteCallback", function)
            return function

        return decorator

    def bound(self, binding: "Group") -> "Command":
        """A copy of the command belonging to a group instance, called with it as `self`.

        Autocompletes defined on the group's class are bound to it too.
        """
        copied = object.__new__(Command)
        for slot in (*_CommandBase.__slots__, *Command.__slots__):
            setattr(copied, slot, getattr(self, slot))
        copied.parameters = [
            dataclasses.replace(parameter, autocomplete=_bind_suggester(parameter.autocomplete, binding))
            for parameter in self.parameters
        ]
        copied.checks = list(self.checks)
        copied.guild_ids = list(self.guild_ids)
        copied.extras = dict(self.extras)
        copied.binding = binding
        copied.parent = None
        return copied

    def to_option(self) -> ApplicationCommandOption:
        """The command as a subcommand option of its group."""
        return ApplicationCommandOption(
            type=ApplicationCommandOptionType.SUB_COMMAND,
            name=self.name,
            description=self.description,
            options=[parameter.to_option() for parameter in self.parameters] or UNSET,
        )

    def to_payload(self) -> OverwriteCommandParams:
        """The command as Bulk Overwrite takes it."""
        payload = self._payload(ApplicationCommandType.CHAT_INPUT)
        payload.description = self.description
        payload.options = [parameter.to_option() for parameter in self.parameters] or UNSET
        return payload

    def arguments(
        self,
        interaction: Interaction,
        options: Sequence[ApplicationCommandInteractionDataOption],
        resolved: ResolvedData | None,
    ) -> dict[str, object]:
        """The keyword arguments the callback receives for these options.

        Raises:
            TransformerError: A required option is missing, or a value cannot be what its parameter
                asks for.
        """
        given = {option.name: option.value for option in options}
        arguments: dict[str, object] = {}
        for parameter in self.parameters:
            value = given.get(parameter.display_name, UNSET)
            if not isinstance(value, UnsetType):
                arguments[parameter.name] = parameter.convert(interaction, value, resolved)
            elif parameter.required:
                raise TransformerError(
                    parameter.display_name, None, "the option is required but was not sent"
                )
            else:
                arguments[parameter.name] = parameter.default
        return arguments

    async def invoke(self, interaction: Interaction, arguments: dict[str, object]) -> None:
        """Run the callback with `arguments`."""
        if self.binding is not None:
            await self.callback(self.binding, interaction, **arguments)
        else:
            await self.callback(interaction, **arguments)

    @override
    def __repr__(self) -> str:
        return f"<Command name={self.qualified_name!r} parameters={len(self.parameters)}>"


def _require(command: Command, name: str) -> Parameter:
    parameter = command.get_parameter(name)
    if parameter is None:
        msg = f"{command.qualified_name!r} has no option {name!r}"
        raise KeyError(msg)
    return parameter


def _bind_suggester(callback: AutocompleteCallback | None, binding: "Group") -> AutocompleteCallback | None:
    """`callback` bound to the group instance when the group's class defines it, as is."""
    defined_here = callback is not None and any(
        member is callback for cls in type(binding).__mro__ for member in vars(cls).values()
    )
    if callback is None or not defined_here:
        return callback
    return cast("AutocompleteCallback", types.MethodType(callback, binding))


def _parameters(
    callback: CommandCallback, pending: _Pending, described: Mapping[str, str]
) -> list[Parameter]:
    """The options a callback declares after the interaction (and `self`, in a group)."""
    found = list(inspect.signature(callback).parameters.values())
    if found and found[0].name == "self":
        found = found[1:]
    if not found:
        msg = f"{callback.__name__} must take the interaction as its first parameter"
        raise TypeError(msg)
    found = found[1:]
    if len(found) > COMMAND_MAX_OPTIONS:
        msg = f"{callback.__name__} has {len(found)} options; Discord takes at most {COMMAND_MAX_OPTIONS}"
        raise ValueError(msg)
    hints = typing.get_type_hints(callback, include_extras=True)
    parameters: list[Parameter] = []
    optional_seen = False
    for item in found:
        if item.kind not in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}:
            msg = f"{callback.__name__}: parameter {item.name!r} must be a plain or keyword-only parameter"
            raise TypeError(msg)
        if item.name not in hints:
            msg = f"{callback.__name__}: parameter {item.name!r} needs a type hint to become an option"
            raise TypeError(msg)
        default = REQUIRED if item.default is inspect.Parameter.empty else item.default
        parameter = parameter_from_annotation(item.name, hints[item.name], default)
        if parameter.required and optional_seen:
            msg = f"{callback.__name__}: required option {item.name!r} must come before optional ones"
            raise TypeError(msg)
        optional_seen = optional_seen or not parameter.required
        parameter.display_name = _check_name(pending.renames.get(item.name, item.name))
        description = pending.descriptions.get(item.name) or described.get(item.name)
        if description:
            parameter.description = _check_description(description, item.name)
        if item.name in pending.choices:
            parameter.choices = pending.choices[item.name]
        parameter.choices = _check_choices(parameter.choices, item.name)
        parameter.autocomplete = pending.autocompletes.get(item.name, parameter.autocomplete)
        parameters.append(parameter)
    return parameters


class Group(_CommandBase):
    """A slash command with subcommands (and, one level down, subgroups).

    Subclass it and decorate methods with `@app_commands.command` (nested `Group` classes become
    subgroups), or create one and add commands with `group.command()`. Class keywords set the
    defaults, and subclasses inherit them: `class Tags(Group, name="tags", description="...")`.

    Discord: https://docs.discord.com/developers/interactions/application-commands#subcommands-and-subcommand-groups
    """

    __slots__ = ("__dict__", "_children", "description", "parent")

    __group_name__: ClassVar[str | None] = None
    __group_description__: ClassVar[str | None] = None
    __group_guild_only__: ClassVar[bool] = False
    __group_nsfw__: ClassVar[bool] = False
    __group_default_permissions__: ClassVar[Permissions | None] = None
    __group_children__: ClassVar[list[tuple[str, "Command | type[Group]"]]] = []
    """The class's commands and nested group classes, made per instance."""

    @override
    def __init_subclass__(
        cls,
        *,
        name: str | None = None,
        description: str | None = None,
        guild_only: bool | None = None,
        nsfw: bool | None = None,
        default_permissions: Permissions | None = None,
    ) -> None:
        """Remember the class's settings (inheriting those it does not give) and its commands."""
        super().__init_subclass__()
        # The name alone is not inherited: a subclass without one is named after its class.
        cls.__group_name__ = None if name is None else _check_name(name)
        if description is not None:
            cls.__group_description__ = description
        if guild_only is not None:
            cls.__group_guild_only__ = guild_only
        if nsfw is not None:
            cls.__group_nsfw__ = nsfw
        if default_permissions is not None:
            cls.__group_default_permissions__ = default_permissions
        found: dict[str, Command | type[Group]] = {}
        for base in reversed(cls.__mro__):
            found.update(
                {
                    attribute: member
                    for attribute, member in vars(base).items()
                    if isinstance(member, Command) or (isinstance(member, type) and issubclass(member, Group))
                }
            )
        cls.__group_children__ = list(found.items())

    def __init__(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        guild_only: bool | None = None,
        nsfw: bool | None = None,
        default_permissions: Permissions | None = None,
        extras: Mapping[str, object] | None = None,
    ) -> None:
        """A group; settings left out come from the class keywords, then the class docstring.

        Raises:
            ValueError: The name or description is not one Discord accepts.
        """
        cls = type(self)
        chosen = _check_name(name or cls.__group_name__ or cls.__name__.lower())
        super().__init__(chosen, _Pending(), extras)
        # Most specific first: the argument, this class's keyword, its docstring, then a base's keyword.
        own_keyword = vars(cls).get("__group_description__")
        summary, _ = _docstring(vars(cls).get("__doc__") if cls is not Group else None)
        self.description: str = _check_description(
            description or own_keyword or summary or cls.__group_description__ or NO_DESCRIPTION, chosen
        )
        self.parent: Group | None = None
        self.guild_only = cls.__group_guild_only__ if guild_only is None else guild_only
        self.nsfw = cls.__group_nsfw__ if nsfw is None else nsfw
        self.default_permissions = (
            cls.__group_default_permissions__ if default_permissions is None else default_permissions
        )
        self._children: dict[str, Command | Group] = {}
        for attribute, child in cls.__group_children__:
            own = child.bound(self) if isinstance(child, Command) else child()
            setattr(self, attribute, own)
            self.add_command(own)

    @property
    def qualified_name(self) -> str:
        """The group's full name: `settings roles`."""
        return f"{self.parent.qualified_name} {self.name}" if self.parent is not None else self.name

    @property
    def commands(self) -> list["Command | Group"]:
        """The subcommands and subgroups."""
        return list(self._children.values())

    def add_command(self, command: "Command | Group") -> Self:
        """Add a subcommand or subgroup.

        Raises:
            ValueError: The name is taken, the group is full (25), the command already belongs to a
                group, or a subgroup would be nested deeper than Discord allows (one level).
        """
        if command.parent is not None:
            msg = f"{command.qualified_name!r} already belongs to a group"
            raise ValueError(msg)
        if command.name in self._children:
            msg = f"{self.qualified_name!r} already has a command named {command.name!r}"
            raise ValueError(msg)
        if len(self._children) >= COMMAND_MAX_OPTIONS:
            msg = f"{self.qualified_name!r} has {COMMAND_MAX_OPTIONS} subcommands, the most Discord allows"
            raise ValueError(msg)
        if isinstance(command, Group) and (
            self.parent is not None or any(isinstance(child, Group) for child in command.commands)
        ):
            msg = "groups can be nested only one level deep"
            raise ValueError(msg)
        command.parent = self
        self._children[command.name] = command
        return self

    def remove_command(self, name: str) -> "Command | Group | None":
        """Remove and return the subcommand or subgroup called `name`."""
        removed = self._children.pop(name, None)
        if removed is not None:
            removed.parent = None
        return removed

    def get_command(self, name: str) -> "Command | Group | None":
        """The subcommand or subgroup called `name`."""
        return self._children.get(name)

    def walk_commands(self) -> Iterator["Command | Group"]:
        """Every subcommand and subgroup, depth first."""
        for child in self._children.values():
            yield child
            if isinstance(child, Group):
                yield from child.walk_commands()

    def command(
        self, *, name: str | None = None, description: str | None = None, nsfw: bool = False
    ) -> Callable[[CommandCallback], Command]:
        """A decorator that adds a subcommand to this group."""

        def decorator(callback: CommandCallback) -> Command:
            created = Command(callback=callback, name=name, description=description, nsfw=nsfw)
            self.add_command(created)
            return created

        return decorator

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Decide whether the group's commands may run; the default allows them."""
        del interaction
        return True

    def to_option(self) -> ApplicationCommandOption:
        """The group as a subcommand-group option of its parent."""
        return ApplicationCommandOption(
            type=ApplicationCommandOptionType.SUB_COMMAND_GROUP,
            name=self.name,
            description=self.description,
            options=[child.to_option() for child in self._children.values()],
        )

    def to_payload(self) -> OverwriteCommandParams:
        """The group as Bulk Overwrite takes it."""
        payload = self._payload(ApplicationCommandType.CHAT_INPUT)
        payload.description = self.description
        payload.options = [child.to_option() for child in self._children.values()]
        return payload

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.qualified_name!r} commands={len(self._children)}>"


class ContextMenu(_CommandBase):
    """A user or message command: right-click a user or a message, then Apps.

    Outside a guild, a user command receives a `User` even when hinted `Member`.

    Discord: https://docs.discord.com/developers/interactions/application-commands#user-commands
    """

    __slots__ = ("callback", "type")

    def __init__(
        self, *, name: str, callback: ContextMenuCallback, extras: Mapping[str, object] | None = None
    ) -> None:
        """A context menu called `name` (any case, spaces allowed, up to 32 characters).

        Its type comes from the second parameter's hint: a `Message` makes a message command, a
        `Member` or `User` a user command.

        Raises:
            TypeError: The callback is not async, or its target's hint is neither.
            ValueError: The name is empty or too long.
        """
        if not inspect.iscoroutinefunction(callback):
            msg = f"the callback of a context menu must be async: {callback!r}"
            raise TypeError(msg)
        if not 1 <= len(name) <= COMMAND_NAME_MAX_LENGTH:
            msg = f"a context menu name has 1 to {COMMAND_NAME_MAX_LENGTH} characters, not {len(name)}"
            raise ValueError(msg)
        super().__init__(name, _pending(callback), extras)
        self.callback: ContextMenuCallback = callback
        self.type: ApplicationCommandType = _context_menu_type(callback)

    @property
    def qualified_name(self) -> str:
        """The menu's name; context menus have no groups."""
        return self.name

    def to_payload(self) -> OverwriteCommandParams:
        """The command as Bulk Overwrite takes it."""
        return self._payload(self.type)

    @override
    def __repr__(self) -> str:
        return f"<ContextMenu name={self.name!r} type={self.type.name}>"


def _context_menu_type(callback: ContextMenuCallback) -> ApplicationCommandType:
    parameters = list(inspect.signature(callback).parameters)
    if len(parameters) != 2:  # noqa: PLR2004 - (interaction, target)
        msg = f"{callback.__name__} must take (interaction, target)"
        raise TypeError(msg)
    target = typing.get_type_hints(callback).get(parameters[1])
    hinted = (
        set(typing.get_args(target))
        if typing.get_origin(target) in {typing.Union, types.UnionType}
        else {target}
    )
    if hinted == {Message}:
        return ApplicationCommandType.MESSAGE
    if hinted <= {Member, User}:
        return ApplicationCommandType.USER
    msg = f"{callback.__name__}: the target must be hinted Message, Member or User"
    raise TypeError(msg)


type AppCommand = Command | Group | ContextMenu
"""Anything a tree registers: a slash command, a group of them, or a context menu."""
type Decoratable = CommandCallback | AppCommand


def command(
    *,
    name: str | None = None,
    description: str | None = None,
    nsfw: bool = False,
    extras: Mapping[str, object] | None = None,
) -> Callable[[CommandCallback], Command]:
    """Turn a function into a command, for a group (`class Tags(Group)`) or `tree.add_command`."""

    def decorator(callback: CommandCallback) -> Command:
        return Command(callback=callback, name=name, description=description, nsfw=nsfw, extras=extras)

    return decorator


def context_menu(
    *, name: str, extras: Mapping[str, object] | None = None
) -> Callable[[ContextMenuCallback], ContextMenu]:
    """Turn a function into a user or message command, for `tree.add_command`."""

    def decorator(callback: ContextMenuCallback) -> ContextMenu:
        return ContextMenu(name=name, callback=callback, extras=extras)

    return decorator


def _apply[T: Decoratable](
    target: T, settle: Callable[[_Pending], None], on_built: Callable[[AppCommand], None]
) -> T:
    """Record a setting on a function not yet a command, or apply it to the command made from it."""
    match target:
        case Command() | Group() | ContextMenu():
            on_built(target)
        case _:
            settle(_pending(target))
    return target


def _options_of(target: AppCommand, decorator: str) -> Command:
    if not isinstance(target, Command):
        msg = f"@{decorator} applies to slash commands, not {type(target).__name__}"
        raise TypeError(msg)
    return target


def describe[T: Decoratable](**descriptions: str) -> Callable[[T], T]:
    """Describe options: `@describe(member="Who to ban")`.

    Raises:
        KeyError: Applied to a command without one of the options.
        TypeError: Applied to a group or a context menu.
        ValueError: A description is empty or longer than 100 characters.
    """
    for name, text in descriptions.items():
        _check_description(text, name)

    def built(target: AppCommand) -> None:
        command = _options_of(target, "describe")
        for name, text in descriptions.items():
            _require(command, name).description = text

    return lambda target: _apply(target, lambda pending: pending.descriptions.update(descriptions), built)


def rename[T: Decoratable](**names: str) -> Callable[[T], T]:
    """Show options under another name: `@rename(member="user")`.

    Raises:
        KeyError: Applied to a command without one of the options.
        TypeError: Applied to a group or a context menu.
        ValueError: A new name is not one Discord accepts.
    """
    for shown in names.values():
        _check_name(shown)

    def built(target: AppCommand) -> None:
        command = _options_of(target, "rename")
        for name, shown in names.items():
            _require(command, name).display_name = shown

    return lambda target: _apply(target, lambda pending: pending.renames.update(names), built)


def choices[T: Decoratable](**options: Sequence[AnyChoice]) -> Callable[[T], T]:
    """Fix an option's choices: `@choices(colour=[Choice(name="Red", value="red")])`.

    Raises:
        KeyError: Applied to a command without one of the options.
        TypeError: Applied to a group or a context menu.
        ValueError: More than 25 choices, or a choice name Discord does not accept.
    """
    checked = {name: _check_choices(listed, name) for name, listed in options.items()}

    def built(target: AppCommand) -> None:
        command = _options_of(target, "choices")
        for name, listed in checked.items():
            _require(command, name).choices = list(listed)

    def settle(pending: _Pending) -> None:
        pending.choices.update({name: list(listed) for name, listed in checked.items()})

    return lambda target: _apply(target, settle, built)


def autocomplete[T: Decoratable](**callbacks: AutocompleteCallback) -> Callable[[T], T]:
    """Suggest an option's values as the user types: `@autocomplete(name=suggest_names)`.

    Raises:
        KeyError: Applied to a command without one of the options.
        TypeError: Applied to a group or a context menu.
    """

    def built(target: AppCommand) -> None:
        command = _options_of(target, "autocomplete")
        for name, callback in callbacks.items():
            _require(command, name).autocomplete = callback

    return lambda target: _apply(target, lambda pending: pending.autocompletes.update(callbacks), built)


def guild_only[T: Decoratable]() -> Callable[[T], T]:
    """Make the command usable only in guilds (not in DMs)."""

    def settle(pending: _Pending) -> None:
        pending.guild_only = True

    def built(target: AppCommand) -> None:
        target.guild_only = True

    return lambda target: _apply(target, settle, built)


def guilds[T: Decoratable](*guild_ids: int) -> Callable[[T], T]:
    """Register the command in these guilds only, instead of globally."""

    def settle(pending: _Pending) -> None:
        pending.guild_ids.extend(guild_ids)

    def built(target: AppCommand) -> None:
        target.guild_ids.extend(guild_ids)

    return lambda target: _apply(target, settle, built)


def default_permissions[T: Decoratable](**permissions: bool) -> Callable[[T], T]:
    """Show the command only to members with these permissions, until a server's admins change it.

    With no permissions, only administrators see it.

    Raises:
        TypeError: A name is not a permission.
    """
    chosen = Permissions(**permissions)

    def settle(pending: _Pending) -> None:
        pending.default_permissions = chosen

    def built(target: AppCommand) -> None:
        target.default_permissions = chosen

    return lambda target: _apply(target, settle, built)


def nsfw[T: Decoratable]() -> Callable[[T], T]:
    """Make the command usable only in age-restricted channels."""

    def settle(pending: _Pending) -> None:
        pending.nsfw = True

    def built(target: AppCommand) -> None:
        target.nsfw = True

    return lambda target: _apply(target, settle, built)


def allowed_contexts[T: Decoratable](
    *, guilds: bool = False, dms: bool = False, private_channels: bool = False
) -> Callable[[T], T]:
    """Where the command can be used: in guilds, in DMs with the bot, in other DMs and group DMs."""
    contexts = [
        context
        for context, allowed in (
            (InteractionContextType.GUILD, guilds),
            (InteractionContextType.BOT_DM, dms),
            (InteractionContextType.PRIVATE_CHANNEL, private_channels),
        )
        if allowed
    ]

    def settle(pending: _Pending) -> None:
        pending.contexts = contexts

    def built(target: AppCommand) -> None:
        target.allowed_contexts = contexts

    return lambda target: _apply(target, settle, built)


def allowed_installs[T: Decoratable](*, guilds: bool = False, users: bool = False) -> Callable[[T], T]:
    """Which installations offer the command: installed to a guild, or to a user's account."""
    installs = [
        install
        for install, allowed in (
            (ApplicationIntegrationType.GUILD_INSTALL, guilds),
            (ApplicationIntegrationType.USER_INSTALL, users),
        )
        if allowed
    ]

    def settle(pending: _Pending) -> None:
        pending.installs = installs

    def built(target: AppCommand) -> None:
        target.allowed_installs = installs

    return lambda target: _apply(target, settle, built)


def check[T: Decoratable](predicate: Check) -> Callable[[T], T]:
    """Run `predicate` before the command; `False` refuses with `CheckFailureError`."""

    def settle(pending: _Pending) -> None:
        pending.checks.append(predicate)

    def built(target: AppCommand) -> None:
        target.add_check(predicate)

    return lambda target: _apply(target, settle, built)
