"""Prefix commands and groups of them.

    @bot.command(aliases=["hi"])
    async def hello(ctx: commands.Context, member: Member) -> None:
        \"\"\"Say hello to someone.\"\"\"
        await ctx.send(f"Hello, {member.mention}!")

    @bot.group(invoke_without_command=True)
    async def tag(ctx: commands.Context) -> None: ...

    @tag.command()
    async def create(ctx: commands.Context, name: str, *, content: str) -> None: ...

A command runs its checks (the bot's, its cog's, then its own), its cooldown and concurrency limit,
parses its arguments, then runs its callback between the `before_invoke` and `after_invoke` hooks.
"""

import asyncio
import copy
import enum
import inspect
import typing
from collections.abc import Awaitable, Callable, Hashable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Self, TypedDict, Unpack, override

from shoal.commands.errors import (
    CheckFailureError,
    CommandError,
    CommandInvokeError,
    CommandOnCooldownError,
    DisabledCommandError,
    MaxConcurrencyReachedError,
    MissingRequiredArgumentError,
    MissingRequiredAttachmentError,
    TooManyArgumentsError,
)
from shoal.commands.parameters import Parameter, parameter_of
from shoal.core.cooldown import AnyCooldown
from shoal.payloads.message import Attachment

if TYPE_CHECKING:
    from shoal.commands.cog import Cog
    from shoal.commands.context import Context

type Check = Callable[["Context"], bool | Awaitable[bool]]
"""A predicate run before the command: return `False` (or raise `CheckFailureError`) to refuse."""
type Hook = Callable[..., Awaitable[None]]
"""Runs before or after a command: `async def(ctx)`, or `async def(self, ctx)` in a cog."""
type ErrorHandler = Callable[..., Awaitable[None]]
"""Handles a command's error: `async def(ctx, error)`, or `async def(self, ctx, error)` in a cog."""
type CommandCallback = Callable[..., Awaitable[None]]
"""`async def name(ctx, ...)`, or `async def name(self, ctx, ...)` in a cog."""

_PENDING: Final = "__shoal_command_settings__"
"""The attribute decorators below `@command` leave on the function, read when the command is made."""


class BucketType(enum.Enum):
    """What a cooldown or a concurrency limit is counted per."""

    DEFAULT = "default"
    """Everyone together."""
    USER = "user"
    GUILD = "guild"
    """Per guild; in DMs, per user."""
    CHANNEL = "channel"
    MEMBER = "member"
    """Per user per guild."""
    CATEGORY = "category"
    """Per channel category; channels outside a category count on their own."""
    ROLE = "role"
    """Per top role; in DMs, per channel."""

    def key(self, ctx: "Context") -> Hashable:
        """What `ctx` counts toward."""
        match self:
            case BucketType.DEFAULT:
                return 0
            case BucketType.USER:
                return ctx.author.id
            case BucketType.GUILD:
                return ctx.guild.id if ctx.guild is not None else ("user", ctx.author.id)
            case BucketType.CHANNEL:
                return ctx.channel.id
            case BucketType.MEMBER:
                return (ctx.guild.id if ctx.guild is not None else None, ctx.author.id)
            case BucketType.CATEGORY:
                return _category_id(ctx)
            case BucketType.ROLE:
                return _top_role_id(ctx)


def _category_id(ctx: "Context") -> Hashable:
    from shoal.models.channel import GuildChannel
    from shoal.models.thread import Thread

    channel = ctx.channel
    if isinstance(channel, Thread):
        parent = channel.parent
        category = parent.category_id if parent is not None else None
    elif isinstance(channel, GuildChannel):
        category = channel.category_id
    else:
        category = None
    return category if category is not None else channel.id


def _top_role_id(ctx: "Context") -> Hashable:
    from shoal.models.member import Member

    author = ctx.author
    if not isinstance(author, Member):
        return ("channel", ctx.channel.id)
    top = author.top_role
    return top.id if top is not None else ctx.guild.id if ctx.guild is not None else author.id


@dataclass(slots=True)
class MaxConcurrency:
    """At most `number` uses running at once per `per` bucket; `wait` queues the rest instead of refusing."""

    number: int
    per: BucketType
    wait: bool = False
    _slots: dict[Hashable, asyncio.Semaphore] = field(default_factory=dict[Hashable, asyncio.Semaphore])
    _users: dict[Hashable, int] = field(default_factory=dict[Hashable, int])
    """How many uses hold or wait for a slot of each key, so an idle key is forgotten."""

    async def acquire(self, ctx: "Context") -> Hashable:
        """Take a slot for `ctx`; the key to release it with.

        Raises:
            MaxConcurrencyReachedError: Every slot is taken and `wait` is off.
        """
        key = self.per.key(ctx)
        slots = self._slots.setdefault(key, asyncio.Semaphore(self.number))
        if slots.locked() and not self.wait:
            raise MaxConcurrencyReachedError(self.number)
        self._users[key] = self._users.get(key, 0) + 1
        try:
            await slots.acquire()
        except BaseException:
            self._leave(key)
            raise
        return key

    def release(self, key: Hashable) -> None:
        """Give back the slot taken for `key`."""
        slots = self._slots.get(key)
        if slots is not None:
            slots.release()
            self._leave(key)

    def _leave(self, key: Hashable) -> None:
        remaining = self._users[key] - 1
        if remaining:
            self._users[key] = remaining
        else:
            del self._users[key]
            del self._slots[key]


@dataclass(slots=True)
class PendingSettings:
    """Settings decorators record on a function before it becomes a command."""

    checks: list[Check] = field(default_factory=list[Check])
    cooldown: AnyCooldown["Context"] | None = None
    max_concurrency: MaxConcurrency | None = None
    before_invoke: Hook | None = None
    after_invoke: Hook | None = None


def pending_of(function: object) -> PendingSettings:
    """The settings decorators have recorded on `function`, created when there are none."""
    found = getattr(function, _PENDING, None)
    if isinstance(found, PendingSettings):
        return found
    created = PendingSettings()
    setattr(function, _PENDING, created)
    return created


def _docstring_summary(function: object) -> str | None:
    doc = inspect.getdoc(function)
    return doc or None


class CommandOptions(TypedDict, total=False):
    """The keywords `Command` takes besides its callback, for the decorators that make one."""

    name: str | None
    aliases: Sequence[str]
    help: str | None
    brief: str | None
    usage: str | None
    description: str
    hidden: bool
    enabled: bool
    ignore_extra: bool
    rest_is_raw: bool
    extras: Mapping[str, object] | None


class GroupOptions(CommandOptions, total=False):
    """The keywords `Group` takes besides its callback."""

    invoke_without_command: bool
    case_insensitive: bool


class Command:
    """A prefix command."""

    __slots__ = (
        "__dict__",
        "_after_invoke",
        "_before_invoke",
        "_error_handler",
        "aliases",
        "brief",
        "callback",
        "checks",
        "cog",
        "cooldown",
        "description",
        "enabled",
        "extras",
        "help",
        "hidden",
        "ignore_extra",
        "is_method",
        "max_concurrency",
        "name",
        "params",
        "parent",
        "rest_is_raw",
        "usage",
    )

    def __init__(
        self,
        callback: CommandCallback,
        /,
        *,
        name: str | None = None,
        aliases: Sequence[str] = (),
        help: str | None = None,  # noqa: A002 - the help text, under the name every bot uses
        brief: str | None = None,
        usage: str | None = None,
        description: str = "",
        hidden: bool = False,
        enabled: bool = True,
        ignore_extra: bool = True,
        rest_is_raw: bool = False,
        extras: Mapping[str, object] | None = None,
    ) -> None:
        """A command running `callback`; its name and help default to the function's name and docstring.

        Raises:
            TypeError: The callback is not async, takes no context, or a parameter's annotation
                cannot be converted to.
        """
        if not inspect.iscoroutinefunction(callback):
            msg = f"the callback of a command must be async: {callback!r}"
            raise TypeError(msg)
        pending = pending_of(callback)
        self.callback: CommandCallback = callback
        self.name: str = name or callback.__name__
        self.aliases: list[str] = list(aliases)
        self.help: str | None = help if help is not None else _docstring_summary(callback)
        self.brief: str | None = brief
        self.usage: str | None = usage
        self.description: str = description
        self.hidden: bool = hidden
        self.enabled: bool = enabled
        self.ignore_extra: bool = ignore_extra
        self.rest_is_raw: bool = rest_is_raw
        self.extras: dict[str, object] = dict(extras or {})
        self.checks: list[Check] = list(pending.checks)
        self.cooldown: AnyCooldown[Context] | None = pending.cooldown
        self.max_concurrency: MaxConcurrency | None = pending.max_concurrency
        self._before_invoke: Hook | None = pending.before_invoke
        self._after_invoke: Hook | None = pending.after_invoke
        self._error_handler: ErrorHandler | None = None
        self.parent: Group | None = None
        self.cog: Cog | None = None
        self.is_method: bool
        self.params: list[Parameter]
        self.is_method, self.params = _parameters(callback)

    @property
    def qualified_name(self) -> str:
        """The command's full name, with its groups: `tag create`."""
        return f"{self.full_parent_name} {self.name}".strip()

    @property
    def full_parent_name(self) -> str:
        """The names of the groups it is in: `tag` for `tag create`."""
        return " ".join(parent.name for parent in reversed(self.parents))

    @property
    def parents(self) -> list["Group"]:
        """Its groups, innermost first."""
        found: list[Group] = []
        parent = self.parent
        while parent is not None:
            found.append(parent)
            parent = parent.parent
        return found

    @property
    def root_parent(self) -> "Group | None":
        """Its outermost group."""
        parents = self.parents
        return parents[-1] if parents else None

    @property
    def short_doc(self) -> str:
        """`brief`, or the first line of the help text."""
        if self.brief is not None:
            return self.brief
        return self.help.split("\n", 1)[0] if self.help else ""

    @property
    def signature(self) -> str:
        """The arguments as help shows them: `<member> [days=1] [reason]`."""
        if self.usage is not None:
            return self.usage
        return " ".join(parameter.usage() for parameter in self.params)

    @property
    def cog_name(self) -> str | None:
        """The name of the cog it belongs to."""
        return self.cog.qualified_name if self.cog is not None else None

    def add_check(self, predicate: Check, /) -> None:
        """Run `predicate` before the command."""
        self.checks.append(predicate)

    def remove_check(self, predicate: Check, /) -> None:
        """Stop running `predicate`."""
        if predicate in self.checks:
            self.checks.remove(predicate)

    def error[F: ErrorHandler](self, handler: F, /) -> F:
        """Handle errors this command raises; `Bot.on_command_error` still runs after it."""
        self._error_handler = handler
        return handler

    @property
    def error_handler(self) -> ErrorHandler | None:
        """The handler set with `error`."""
        return self._error_handler

    def before_invoke[F: Hook](self, hook: F, /) -> F:
        """Run `hook` after the checks and parsing, just before the callback."""
        self._before_invoke = hook
        return hook

    def after_invoke[F: Hook](self, hook: F, /) -> F:
        """Run `hook` after the callback, even when it raised."""
        self._after_invoke = hook
        return hook

    def bound(self, cog: "Cog") -> Self:
        """A copy of the command belonging to a cog instance, called with it as `self`."""
        copied = self.copy()
        copied.cog = cog
        return copied

    def copy(self) -> Self:
        """A copy with its own checks and settings (every subclass's slots included)."""
        copied = copy.copy(self)
        copied.checks = list(self.checks)
        copied.aliases = list(self.aliases)
        copied.extras = dict(self.extras)
        return copied

    async def can_run(self, ctx: "Context") -> bool:
        """Whether every check passes for `ctx`: the bot's, the cog's, then the command's.

        Raises:
            CheckFailureError: A check refused (directly, or by returning `False`).
            DisabledCommandError: The command is disabled.
        """
        if not self.enabled:
            raise DisabledCommandError(self.qualified_name)
        original = ctx.command
        ctx.command = self
        try:
            if not await ctx.bot.can_run(ctx):
                msg = f"the global check functions for command {self.qualified_name} failed"
                raise CheckFailureError(msg)
            if self.cog is not None and not await _passes(self.cog.cog_check, ctx):
                msg = f"the cog check for command {self.qualified_name} failed"
                raise CheckFailureError(msg)
            for predicate in self.checks:
                if not await _passes(predicate, ctx):
                    msg = f"a check of command {self.qualified_name} failed"
                    raise CheckFailureError(msg)
            return True
        finally:
            ctx.command = original

    def retry_after(self, ctx: "Context") -> float:
        """Seconds until `ctx` may use the command again without recording a use; 0.0 when allowed now."""
        return 0.0 if self.cooldown is None else self.cooldown.get_retry_after(ctx)

    def reset_cooldown(self, ctx: "Context") -> None:
        """Forget `ctx`'s uses, so the next one is allowed."""
        if self.cooldown is not None:
            self.cooldown.reset(ctx)

    async def prepare(self, ctx: "Context") -> None:
        """Run the checks and the cooldown, then parse the arguments into `ctx.args` and `ctx.kwargs`.

        Raises:
            CommandError: A check refused, the command is on cooldown, or an argument is wrong.
        """
        await self.ready(ctx)
        await self.parse_arguments(ctx)

    async def ready(self, ctx: "Context") -> None:
        """Run the checks, then record a use against the cooldown.

        Raises:
            CheckFailureError: A check refused.
            CommandOnCooldownError: The cooldown has no room for `ctx`.
            DisabledCommandError: The command is disabled.
        """
        ctx.command = self
        await self.can_run(ctx)
        if self.cooldown is not None:
            wait = self.cooldown.update_rate_limit(ctx)
            if wait > 0:
                raise CommandOnCooldownError(wait)

    async def parse_arguments(self, ctx: "Context") -> None:
        """Convert the words after the command into `ctx.args` and `ctx.kwargs`.

        Raises:
            UserInputError: An argument is missing, extra, quoted wrong, or does not convert.
        """
        ctx.args = []
        ctx.kwargs = {}
        view = ctx.view
        attachments = list(ctx.message.attachments) if ctx.message is not None else []
        for parameter in self.params:
            ctx.current_parameter = parameter
            if parameter.kind == "attachment":
                ctx.args.append(await _attachment(ctx, parameter, attachments))
                continue
            if parameter.kind == "every_word":
                ctx.args.extend(await _every_word(ctx, parameter))
                break
            if parameter.consumes_rest:
                ctx.kwargs[parameter.name] = await _rest(ctx, parameter, raw=self.rest_is_raw)
                break
            ctx.args.append(await _one(ctx, parameter))
        ctx.current_parameter = None
        view.skip_ws()
        if not self.ignore_extra and not view.at_end():
            raise TooManyArgumentsError(view.read_rest())

    async def invoke(self, ctx: "Context") -> None:
        """Prepare, then run the callback between the hooks.

        Raises:
            CommandError: The command could not run, or its callback raised (as `CommandInvokeError`).
        """
        await self.prepare(ctx)
        await self.run(ctx)

    async def run(self, ctx: "Context") -> None:
        """Run the callback with the parsed arguments, between the hooks, within the concurrency limit."""
        held = await self.max_concurrency.acquire(ctx) if self.max_concurrency is not None else None
        try:
            await self._hooks("before", ctx)
            try:
                await self.call(ctx, ctx.args, ctx.kwargs)
            finally:
                await self._hooks("after", ctx)
        finally:
            if held is not None and self.max_concurrency is not None:
                self.max_concurrency.release(held)

    async def _hooks(self, when: typing.Literal["before", "after"], ctx: "Context") -> None:
        own = self._before_invoke if when == "before" else self._after_invoke
        cog_hook = None
        if self.cog is not None:
            cog_hook = self.cog.cog_before_invoke if when == "before" else self.cog.cog_after_invoke
        bot_hook = ctx.bot.before_invoke_hook if when == "before" else ctx.bot.after_invoke_hook
        for hook in (cog_hook, own, bot_hook) if when == "before" else (own, cog_hook, bot_hook):
            if hook is not None:
                await self._call_with_binding(hook, ctx)

    async def _call_with_binding(self, hook: Hook, ctx: "Context") -> None:
        if self.cog is not None and _takes_self(hook) and not inspect.ismethod(hook):
            await hook(self.cog, ctx)
        else:
            await hook(ctx)

    async def call(self, ctx: "Context", args: Sequence[object], kwargs: Mapping[str, object]) -> None:
        """Run the callback with these arguments, as `CommandInvokeError` when it raises.

        Raises:
            CommandInvokeError: The callback raised something other than a command error.
        """
        try:
            if self.is_method:
                await self.callback(self.cog, ctx, *args, **kwargs)
            else:
                await self.callback(ctx, *args, **kwargs)
        except CommandError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise CommandInvokeError(self.qualified_name, error) from error

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.qualified_name!r}>"


async def _passes(predicate: Callable[["Context"], bool | Awaitable[bool]], ctx: "Context") -> bool:
    result = predicate(ctx)
    return bool(await result if inspect.isawaitable(result) else result)


def _takes_self(function: Callable[..., object]) -> bool:
    parameters = list(inspect.signature(function).parameters)
    return bool(parameters) and parameters[0] == "self"


async def _one(ctx: "Context", parameter: Parameter) -> object:
    """One positional argument: a word (or quoted text), or as many words as convert for `Greedy`."""
    view = ctx.view
    if parameter.greedy:
        converted: list[object] = []
        while True:
            view.skip_ws()
            if view.at_end():
                break
            start = view.index
            word = view.get_quoted_word()
            if word is None:
                break
            try:
                converted.append(await parameter.converter(ctx, word))
            except CommandError:
                view.index = start
                break
        if not converted and not parameter.has_default:
            raise MissingRequiredArgumentError(parameter)
        return converted or await parameter.default_for(ctx)
    view.skip_ws()
    if view.at_end():
        if parameter.required:
            raise MissingRequiredArgumentError(parameter)
        return await parameter.default_for(ctx)
    start = view.index
    word = view.get_quoted_word()
    if word is None:
        return await parameter.default_for(ctx)
    ctx.current_argument = word
    try:
        return await parameter.converter(ctx, word)
    except CommandError:
        if not parameter.optional:
            raise
        view.index = start
        return await parameter.default_for(ctx)


async def _attachment(ctx: "Context", parameter: Parameter, attachments: list[Attachment]) -> object:
    """The next attached file (or, for `Greedy`, every one left); they are taken in order."""
    if parameter.greedy:
        taken = list(attachments)
        attachments.clear()
        if taken:
            return taken
    elif attachments:
        return attachments.pop(0)
    if parameter.required:
        raise MissingRequiredAttachmentError(parameter)
    return await parameter.default_for(ctx)


async def _every_word(ctx: "Context", parameter: Parameter) -> list[object]:
    view = ctx.view
    converted: list[object] = []
    while True:
        view.skip_ws()
        word = view.get_quoted_word()
        if word is None:
            return converted
        ctx.current_argument = word
        converted.append(await parameter.converter(ctx, word))


async def _rest(ctx: "Context", parameter: Parameter, *, raw: bool) -> object:
    view = ctx.view
    view.skip_ws()
    if view.at_end():
        if parameter.required:
            raise MissingRequiredArgumentError(parameter)
        return await parameter.default_for(ctx)
    rest = view.read_rest()
    argument = rest if raw else rest.strip()
    ctx.current_argument = argument
    return await parameter.converter(ctx, argument)


def _parameters(callback: CommandCallback) -> tuple[bool, list[Parameter]]:
    """Whether the callback is a method (takes `self`), and its parameters after the context."""
    found = list(inspect.signature(callback).parameters.values())
    is_method = bool(found) and found[0].name == "self"
    if is_method:
        found = found[1:]
    if not found:
        msg = f"{callback.__name__} must take the context as its first parameter"
        raise TypeError(msg)
    hints = typing.get_type_hints(callback, include_extras=True)
    parameters: list[Parameter] = []
    for item in found[1:]:
        if item.kind is inspect.Parameter.VAR_KEYWORD:
            msg = f"{callback.__name__}: **{item.name} cannot hold command arguments"
            raise TypeError(msg)
        if item.kind is inspect.Parameter.POSITIONAL_ONLY:
            msg = f"{callback.__name__}: parameter {item.name!r} cannot be positional-only"
            raise TypeError(msg)
        parameters.append(parameter_of(item, hints.get(item.name, item.annotation)))
    rest = [item for item in parameters if item.consumes_rest]
    if len(rest) > 1:
        msg = f"{callback.__name__}: only one keyword-only parameter can take the rest of the message"
        raise TypeError(msg)
    every = next((index for index, item in enumerate(parameters) if item.kind == "every_word"), None)
    if every is not None:
        # *args takes every word left, so nothing after it is ever given one.
        unfilled = [item.name for item in parameters[every + 1 :] if item.required]
        if unfilled:
            star = parameters[every].name
            msg = f"{callback.__name__}: {', '.join(unfilled)} after *{star} needs a default"
            raise TypeError(msg)
    return is_method, parameters


class Group(Command):
    """A command with subcommands: `!tag create`, `!tag delete`."""

    __slots__ = ("_commands", "case_insensitive", "invoke_without_command")

    def __init__(
        self,
        callback: CommandCallback,
        /,
        *,
        invoke_without_command: bool = False,
        case_insensitive: bool = False,
        name: str | None = None,
        aliases: Sequence[str] = (),
        help: str | None = None,  # noqa: A002 - the help text, under the name every bot uses
        brief: str | None = None,
        usage: str | None = None,
        description: str = "",
        hidden: bool = False,
        enabled: bool = True,
        ignore_extra: bool = True,
        rest_is_raw: bool = False,
        extras: Mapping[str, object] | None = None,
    ) -> None:
        """A group; with `invoke_without_command` its own callback runs only without a subcommand.

        Raises:
            TypeError: As for `Command`.
        """
        super().__init__(
            callback,
            name=name,
            aliases=aliases,
            help=help,
            brief=brief,
            usage=usage,
            description=description,
            hidden=hidden,
            enabled=enabled,
            ignore_extra=ignore_extra,
            rest_is_raw=rest_is_raw,
            extras=extras,
        )
        self.invoke_without_command: bool = invoke_without_command
        self.case_insensitive: bool = case_insensitive
        self._commands: dict[str, Command] = {}

    @property
    def commands(self) -> list[Command]:
        """Its subcommands, each once (aliases are not repeated)."""
        return list(dict.fromkeys(self._commands.values()))

    def add_command(self, command: Command, /) -> None:
        """Add a subcommand.

        Raises:
            CommandRegistrationError: Its name or an alias is taken.
        """
        register_command(self._commands, command, case_insensitive=self.case_insensitive)
        command.parent = self

    def remove_command(self, name: str, /) -> Command | None:
        """Remove the subcommand called `name` (or with that alias), with its aliases."""
        removed = self.get_command(name)
        if removed is not None:
            unregister_command(self._commands, removed, case_insensitive=self.case_insensitive)
            removed.parent = None
        return removed

    def get_command(self, name: str, /) -> Command | None:
        """The subcommand called `name` (or with that alias); `tag edit` finds nested ones."""
        return lookup_command(self._commands, name, case_insensitive=self.case_insensitive)

    def walk_commands(self) -> Iterator[Command]:
        """Every subcommand, depth first."""
        for command in self.commands:
            yield command
            if isinstance(command, Group):
                yield from command.walk_commands()

    def command(self, **options: Unpack[CommandOptions]) -> Callable[[CommandCallback], Command]:
        """A decorator that adds a subcommand (keywords as for `Command`)."""

        def decorator(callback: CommandCallback) -> Command:
            created = Command(callback, **options)
            self.add_command(created)
            return created

        return decorator

    def group(self, **options: Unpack[GroupOptions]) -> Callable[[CommandCallback], "Group"]:
        """A decorator that adds a subgroup (keywords as for `Group`)."""

        def decorator(callback: CommandCallback) -> Group:
            created = Group(callback, **options)
            self.add_command(created)
            return created

        return decorator

    @override
    def copy(self) -> Self:
        copied = super().copy()
        # Registered directly, not through `add_command`, which a subclass may extend (a hybrid
        # group adds slash subcommands there) before the copy has state of its own.
        copied._commands = {}  # noqa: SLF001 - the copy is this class's own
        for command in self.commands:
            child = command.copy()
            register_command(copied._commands, child, case_insensitive=self.case_insensitive)  # noqa: SLF001
            child.parent = copied
        return copied

    @override
    def bound(self, cog: "Cog") -> Self:
        copied = self.copy()
        copied.cog = cog
        for command in copied.walk_commands():
            command.cog = cog
        return copied

    @override
    async def invoke(self, ctx: "Context") -> None:
        ctx.invoked_subcommand = None
        ctx.subcommand_passed = None
        early = not self.invoke_without_command
        if early:
            await self.prepare(ctx)
        view = ctx.view
        previous = view.index
        view.skip_ws()
        trigger = view.get_word()
        if trigger:
            ctx.subcommand_passed = trigger
            ctx.invoked_subcommand = self.get_command(trigger)
        if early:
            await self.run(ctx)
        if trigger and ctx.invoked_subcommand is not None:
            ctx.invoked_parents.append(ctx.invoked_with or self.name)
            ctx.invoked_with = trigger
            await ctx.invoked_subcommand.invoke(ctx)
        elif not early:
            view.index = previous
            view.previous = previous
            await super().invoke(ctx)


class CommandRegistrationError(CommandError):
    """A command's name or alias is already taken."""

    def __init__(self, name: str, *, alias_conflict: bool = False) -> None:
        """`name` is taken."""
        kind = "alias" if alias_conflict else "command"
        super().__init__(f"the {kind} {name!r} is already an existing command or alias")
        self.name: str = name
        self.alias_conflict: bool = alias_conflict


def register_command(table: dict[str, Command], command: Command, *, case_insensitive: bool) -> None:
    """Add `command` to `table` under its name and aliases.

    Raises:
        CommandRegistrationError: The name or an alias is taken; nothing is added.
    """
    keys = [command.name, *command.aliases]
    folded = [key.casefold() if case_insensitive else key for key in keys]
    for index, key in enumerate(folded):
        if key in table:
            raise CommandRegistrationError(keys[index], alias_conflict=index > 0)
    for key in folded:
        table[key] = command


def unregister_command(table: dict[str, Command], command: Command, *, case_insensitive: bool) -> None:
    """Remove `command`'s name and aliases from `table`."""
    for key in (command.name, *command.aliases):
        folded = key.casefold() if case_insensitive else key
        if table.get(folded) is command:
            del table[folded]


def lookup_command(table: Mapping[str, Command], name: str, *, case_insensitive: bool) -> Command | None:
    """The command `name` names in `table`; `tag create` looks inside group `tag`."""
    first, _, rest = name.strip().partition(" ")
    found = table.get(first.casefold() if case_insensitive else first)
    if not rest or found is None:
        return found
    return found.get_command(rest) if isinstance(found, Group) else None


def command(**options: Unpack[CommandOptions]) -> Callable[[CommandCallback], Command]:
    """Turn a function into a command, for a cog or `bot.add_command` (keywords as for `Command`)."""

    def decorator(callback: CommandCallback) -> Command:
        return Command(callback, **options)

    return decorator


def group(**options: Unpack[GroupOptions]) -> Callable[[CommandCallback], Group]:
    """Turn a function into a group of commands, for a cog or `bot.add_command` (keywords as for `Group`)."""

    def decorator(callback: CommandCallback) -> Group:
        return Group(callback, **options)

    return decorator
