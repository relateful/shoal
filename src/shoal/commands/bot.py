"""`Bot`: a client with prefix commands, hybrid commands, slash commands, cogs and extensions.

    bot = commands.Bot(command_prefix="!", intents=Intents.default() | Intents.message_content)

    @bot.command()
    async def ping(ctx: commands.Context) -> None:
        await ctx.send("Pong")

    bot.run(token)

Prefix commands need the message content intent (privileged, enabled in the Developer Portal), except
in DMs and in messages that mention the bot. `bot.tree` holds the slash commands; hybrid commands
are added to it automatically.
"""

import importlib
import importlib.util
import inspect
import logging
import sys
import types
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from typing import Final, Unpack, override

from msgspec import UnsetType

from shoal.app_commands.commands import Command as AppCommandBase
from shoal.app_commands.commands import Group as AppGroup
from shoal.app_commands.tree import CommandTree
from shoal.client.client import Client, ClientOptions, Listener
from shoal.client.interaction import Interaction
from shoal.commands.cog import Cog
from shoal.commands.context import Context
from shoal.commands.core import (
    Check,
    Command,
    CommandCallback,
    CommandOptions,
    Group,
    GroupOptions,
    Hook,
    lookup_command,
    register_command,
    unregister_command,
)
from shoal.commands.errors import (
    CommandError,
    CommandNotFoundError,
    ExtensionAlreadyLoadedError,
    ExtensionFailedError,
    ExtensionNotFoundError,
    ExtensionNotLoadedError,
    NoEntryPointError,
)
from shoal.commands.help import DefaultHelpCommand, HelpCommand
from shoal.commands.hybrid import HybridCommand, HybridGroup
from shoal.commands.view import StringView
from shoal.models.base import Hashable
from shoal.models.message import Message
from shoal.payloads.gateway import Intents

_log = logging.getLogger("shoal.commands")

type PrefixResult = str | Sequence[str]
type Prefix = PrefixResult | Callable[["Bot", Message], PrefixResult | Awaitable[PrefixResult]]
"""A prefix, several, or a function of the bot and the message that returns them."""


class _DefaultHelp:
    """The `help_command` default: a `DefaultHelpCommand`."""

    __slots__ = ()


DEFAULT_HELP: Final = _DefaultHelp()


def when_mentioned(bot: "Bot", message: Message) -> list[str]:
    """Use mentioning the bot as the prefix: `@Bot ping`."""
    del message
    user = bot.user
    if user is None:
        return []
    return [f"<@{int(user.id)}> ", f"<@!{int(user.id)}> "]


def when_mentioned_or(*prefixes: str) -> Callable[["Bot", Message], list[str]]:
    """Use mentioning the bot or any of `prefixes`: `when_mentioned_or("!", "?")`."""

    def prefix(bot: "Bot", message: Message) -> list[str]:
        return [*when_mentioned(bot, message), *prefixes]

    return prefix


class Bot(Client):
    """A client with commands; it takes `Client`'s arguments, and these.

    Args:
        command_prefix: What starts a command: a string, several, or a function of the bot and
            the message that returns them (`when_mentioned_or("!")`).
        help_command: The help command; `None` for none.
        description: Shown at the top of the default help.
        case_insensitive: Match command names in any case.
        strip_after_prefix: Allow spaces between the prefix and the command (`! ping`).
        owner_id: The owner, for `is_owner`; by default the application's owner (or its team).
        owner_ids: Several owners instead.
        context_class: The `Context` subclass commands receive.
        options: `Client`'s other keywords (`ClientOptions`): cache, sharding, presence, the REST
            client, the application's emojis, metrics, sessions, the cache snapshot, the identify
            limiter, the shard directory, the command router, the cluster name, the clock and the
            shards' connection settings.
    """

    __slots__ = (
        "_cogs",
        "_commands",
        "_extensions",
        "_help_command",
        "_owner_lookup_done",
        "after_invoke_hook",
        "before_invoke_hook",
        "case_insensitive",
        "checks",
        "command_prefix",
        "context_class",
        "description",
        "owner_id",
        "owner_ids",
        "strip_after_prefix",
        "tree",
    )

    def __init__(
        self,
        command_prefix: Prefix,
        *,
        intents: Intents,
        help_command: HelpCommand | _DefaultHelp | None = DEFAULT_HELP,
        description: str | None = None,
        case_insensitive: bool = False,
        strip_after_prefix: bool = False,
        owner_id: int | None = None,
        owner_ids: Sequence[int] = (),
        context_class: type[Context] = Context,
        **options: Unpack[ClientOptions],
    ) -> None:
        """Create a bot; see the class docstring for the arguments.

        Raises:
            TypeError: Both `owner_id` and `owner_ids` were given.
        """
        if owner_id is not None and owner_ids:
            msg = "give owner_id or owner_ids, not both"
            raise TypeError(msg)
        super().__init__(intents=intents, **options)
        self.command_prefix: Prefix = command_prefix
        self.description: str | None = description
        self.case_insensitive: bool = case_insensitive
        self.strip_after_prefix: bool = strip_after_prefix
        self.owner_id: int | None = owner_id
        self.owner_ids: set[int] = set(owner_ids)
        self._owner_lookup_done: bool = owner_id is not None or bool(owner_ids)
        self.context_class: type[Context] = context_class
        self.checks: list[Check] = []
        self.before_invoke_hook: Hook | None = None
        self.after_invoke_hook: Hook | None = None
        self.tree: CommandTree = CommandTree(self)
        self._commands: dict[str, Command] = {}
        self._cogs: dict[str, Cog] = {}
        self._extensions: dict[str, types.ModuleType] = {}
        self._help_command: HelpCommand | None = None
        self.help_command = DefaultHelpCommand() if isinstance(help_command, _DefaultHelp) else help_command

    # The commands the bot runs.

    @property
    def commands(self) -> list[Command]:
        """Every top-level command, each once."""
        return list(dict.fromkeys(self._commands.values()))

    def get_command(self, name: str, /) -> Command | None:
        """The command called `name` (or with that alias); `tag create` finds subcommands."""
        return lookup_command(self._commands, name, case_insensitive=self.case_insensitive)

    def walk_commands(self) -> Iterator[Command]:
        """Every command and subcommand, depth first."""
        for command in self.commands:
            yield command
            if isinstance(command, Group):
                yield from command.walk_commands()

    def add_command(self, command: Command, /) -> None:
        """Add a command; a hybrid command's slash side is added to `tree` too.

        Raises:
            CommandRegistrationError: Its name or an alias is taken.
            ValueError: The slash side's name is taken in `tree`.
        """
        slash = _top_level_slash(command)
        if slash is not None:
            self.tree.add_command(slash)
        try:
            register_command(self._commands, command, case_insensitive=self.case_insensitive)
        except CommandError:
            if slash is not None:
                self.tree.discard(slash)
            raise

    def remove_command(self, name: str, /) -> Command | None:
        """Remove the command called `name` (or with that alias), with its slash side."""
        removed = self._commands.get(name.casefold() if self.case_insensitive else name)
        if removed is None:
            return None
        unregister_command(self._commands, removed, case_insensitive=self.case_insensitive)
        slash = _top_level_slash(removed)
        if slash is not None:
            self.tree.discard(slash)
        return removed

    def command(self, **options: Unpack[CommandOptions]) -> Callable[[CommandCallback], Command]:
        """A decorator that makes a prefix command and adds it."""

        def decorator(callback: CommandCallback) -> Command:
            created = Command(callback, **options)
            self.add_command(created)
            return created

        return decorator

    def group(self, **options: Unpack[GroupOptions]) -> Callable[[CommandCallback], Group]:
        """A decorator that makes a group of prefix commands and adds it."""

        def decorator(callback: CommandCallback) -> Group:
            created = Group(callback, **options)
            self.add_command(created)
            return created

        return decorator

    def hybrid_command(self, **options: Unpack[CommandOptions]) -> Callable[[CommandCallback], HybridCommand]:
        """A decorator that makes a command used both with the prefix and as a slash command."""

        def decorator(callback: CommandCallback) -> HybridCommand:
            created = HybridCommand(callback, **options)
            self.add_command(created)
            return created

        return decorator

    def hybrid_group(self, **options: Unpack[GroupOptions]) -> Callable[[CommandCallback], HybridGroup]:
        """A decorator that makes a group used both with the prefix and as a slash command."""

        def decorator(callback: CommandCallback) -> HybridGroup:
            created = HybridGroup(callback, **options)
            self.add_command(created)
            return created

        return decorator

    # Checks and hooks for every command.

    def check[F: Check](self, predicate: F, /) -> F:
        """Run `predicate` before every prefix and hybrid command."""
        self.checks.append(predicate)
        return predicate

    def add_check(self, predicate: Check, /) -> None:
        """Run `predicate` before every prefix and hybrid command."""
        self.checks.append(predicate)

    def remove_check(self, predicate: Check, /) -> None:
        """Stop running `predicate`."""
        if predicate in self.checks:
            self.checks.remove(predicate)

    async def can_run(self, ctx: Context) -> bool:
        """Whether every global check passes for `ctx`."""
        for predicate in self.checks:
            result = predicate(ctx)
            if not (await result if inspect.isawaitable(result) else result):
                return False
        return True

    def before_invoke[F: Hook](self, hook: F, /) -> F:
        """Run `hook` before every command's callback."""
        self.before_invoke_hook = hook
        return hook

    def after_invoke[F: Hook](self, hook: F, /) -> F:
        """Run `hook` after every command's callback."""
        self.after_invoke_hook = hook
        return hook

    # The help command.

    @property
    def help_command(self) -> HelpCommand | None:
        """The help command, added as a command called `help` (or its `command_name`)."""
        return self._help_command

    @help_command.setter
    def help_command(self, value: HelpCommand | None) -> None:
        if self._help_command is not None:
            self.remove_command(self._help_command.command_name)
        self._help_command = value
        if value is not None:
            self.add_command(_help_command(value))

    async def send_help(self, ctx: Context, entity: Command | str | None = None) -> None:
        """Show the help command's page for the bot, a command or a cog (as `!help` would)."""
        helper = self._help_command
        if helper is None:
            return
        query = entity.qualified_name if isinstance(entity, Command) else entity
        await helper.command_callback(ctx, query)

    @property
    def cogs(self) -> Mapping[str, Cog]:
        """The cogs added, by name."""
        return dict(self._cogs)

    def get_cog(self, name: str, /) -> Cog | None:
        """The cog called `name`."""
        return self._cogs.get(name)

    async def add_cog(self, cog: Cog, /, *, override: bool = False) -> None:
        """Add a cog's commands, slash commands and listeners, after its `cog_load`.

        Raises:
            ValueError: A cog of that name is already added (pass `override=True` to replace it).
            CommandRegistrationError: A command's name is taken; nothing of the cog is added.
            ValueError: A slash command's name is taken in `tree`; nothing of the cog is added.
            TypeError: A listener is not a coroutine function; nothing of the cog is added.
        """
        name = cog.qualified_name
        if name in self._cogs:
            if not override:
                msg = f"a cog named {name!r} is already added"
                raise ValueError(msg)
            await self.remove_cog(name)
        cog.bind()
        await cog.cog_load()
        added: list[Command] = []
        added_to_tree: list[AppCommandBase | AppGroup] = []
        listening: list[tuple[str, Listener]] = []
        try:
            for command in cog.get_commands():
                self.add_command(command)
                added.append(command)
            for app_command in cog.get_app_commands():
                _attach_cog(app_command, cog)
                self.tree.add_command(app_command)
                added_to_tree.append(app_command)
            for event, method in cog.get_listeners():
                listener = _as_listener(method)
                self.add_listener(listener, event)
                listening.append((event, listener))
        except BaseException:
            for command in added:
                self.remove_command(command.name)
            for app_command in added_to_tree:
                self.tree.discard(app_command)
            for event, listener in listening:
                self.remove_listener(listener, event)
            await cog.cog_unload()
            raise
        self._cogs[name] = cog

    async def remove_cog(self, name: str, /) -> Cog | None:
        """Remove a cog's commands, slash commands and listeners, then run its `cog_unload`."""
        cog = self._cogs.pop(name, None)
        if cog is None:
            return None
        for command in cog.get_commands():
            if self.get_command(command.name) is command:
                self.remove_command(command.name)
        for app_command in cog.get_app_commands():
            self.tree.discard(app_command)
        for event, method in cog.get_listeners():
            self.remove_listener(_as_listener(method), event)
        await cog.cog_unload()
        return cog

    @property
    def extensions(self) -> Mapping[str, types.ModuleType]:
        """The extensions loaded, by module name."""
        return dict(self._extensions)

    async def load_extension(self, name: str, *, package: str | None = None) -> None:
        """Import module `name` and run its `async def setup(bot)`.

        The import runs on the event loop, as Python imports do; load extensions at start-up
        (`setup_hook`), not while the bot is busy.

        Raises:
            ExtensionNotFoundError: No module is called `name`.
            ExtensionAlreadyLoadedError: It is already loaded.
            NoEntryPointError: The module has no `setup`.
            ExtensionFailedError: Importing it or its `setup` raised; nothing of it stays added.
        """
        resolved = _resolve(name, package)
        if resolved in self._extensions:
            raise ExtensionAlreadyLoadedError(resolved)
        spec = importlib.util.find_spec(resolved)
        if spec is None or spec.loader is None:
            raise ExtensionNotFoundError(resolved)
        module = importlib.util.module_from_spec(spec)
        sys.modules[resolved] = module
        try:
            spec.loader.exec_module(module)
        except Exception as error:
            del sys.modules[resolved]
            raise ExtensionFailedError(resolved, error) from error
        setup = getattr(module, "setup", None)
        if setup is None or not inspect.iscoroutinefunction(setup):
            del sys.modules[resolved]
            raise NoEntryPointError(resolved)
        try:
            await setup(self)
        except Exception as error:
            await self._forget_module(resolved)
            del sys.modules[resolved]
            raise ExtensionFailedError(resolved, error) from error
        self._extensions[resolved] = module

    async def unload_extension(self, name: str, *, package: str | None = None) -> None:
        """Run the extension's `async def teardown(bot)` if it has one, and remove what it added.

        Raises:
            ExtensionNotLoadedError: It is not loaded.
        """
        resolved = _resolve(name, package)
        module = self._extensions.pop(resolved, None)
        if module is None:
            raise ExtensionNotLoadedError(resolved)
        teardown = getattr(module, "teardown", None)
        if teardown is not None and inspect.iscoroutinefunction(teardown):
            try:
                await teardown(self)
            except Exception:  # noqa: BLE001 - unloading goes on; the error is logged
                _log.exception("teardown of extension %s raised", resolved)
        await self._forget_module(resolved)
        for loaded in [key for key in sys.modules if key == resolved or key.startswith(f"{resolved}.")]:
            del sys.modules[loaded]

    async def reload_extension(self, name: str, *, package: str | None = None) -> None:
        """Unload and load the extension again; when loading fails, the old version is restored.

        Raises:
            ExtensionNotLoadedError: It is not loaded.
            ExtensionFailedError: The new version failed to load (the old one is back).
        """
        resolved = _resolve(name, package)
        old = self._extensions.get(resolved)
        if old is None:
            raise ExtensionNotLoadedError(resolved)
        kept = {
            key: module
            for key, module in sys.modules.items()
            if key == resolved or key.startswith(f"{resolved}.")
        }
        await self.unload_extension(resolved)
        try:
            await self.load_extension(resolved)
        except Exception:
            sys.modules.update(kept)
            setup = getattr(old, "setup", None)
            try:
                if setup is not None:
                    await setup(self)
            except Exception:  # noqa: BLE001 - the failed load's error is the one to raise
                _log.exception("restoring extension %s after a failed reload raised", resolved)
            self._extensions[resolved] = old
            raise

    async def _forget_module(self, module: str) -> None:
        """Remove the cogs, commands and listeners that module `module` (or its submodules) defined."""

        def defined_in(value: object) -> bool:
            name = getattr(value, "__module__", None)
            return isinstance(name, str) and (name == module or name.startswith(f"{module}."))

        for cog_name, cog in list(self._cogs.items()):
            if defined_in(type(cog)):
                await self.remove_cog(cog_name)
        for command in self.commands:
            if defined_in(command.callback):
                self.remove_command(command.name)
        # What `setup` added to the tree directly (`@bot.tree.command`, `bot.tree.add_command`).
        for app_command in self.tree.get_all_commands():
            if isinstance(app_command, AppGroup):
                own = defined_in(type(app_command)) or any(
                    defined_in(child.callback)
                    for child in app_command.walk_commands()
                    if isinstance(child, AppCommandBase)
                )
            else:
                own = defined_in(app_command.callback)
            if own:
                self.tree.discard(app_command)
        for event, listeners in list(self._listeners.items()):
            for listener in list(listeners):
                if defined_in(listener):
                    self.remove_listener(listener, event)

    async def is_owner(self, user: Hashable, /) -> bool:
        """Whether `user` owns the bot: `owner_id`/`owner_ids`, or the application's owner or team.

        The application is fetched once, the first time this is asked.
        """
        if not self._owner_lookup_done:
            application = await self.rest.applications.get_me()
            if application.team is not None:
                self.owner_ids = {int(member.user.id) for member in application.team.members}
            elif not isinstance(application.owner, UnsetType):
                self.owner_id = int(application.owner.id)
            self._owner_lookup_done = True
        return user.id == self.owner_id or user.id in self.owner_ids

    # Running commands.

    async def get_prefix(self, message: Message) -> str | list[str]:
        """The prefix (or prefixes) for `message`."""
        prefix = self.command_prefix
        result = prefix(self, message) if callable(prefix) else prefix
        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, str) else list(result)

    async def get_context[C: Context](self, message: Message, *, cls: type[C] | None = None) -> C | Context:
        """The context for `message`: its prefix and command, when it uses one (`ctx.valid`)."""
        view = StringView(message.content)
        context_class = cls or self.context_class
        ctx = context_class(self, message, view=view)
        prefix = await self.get_prefix(message)
        prefixes = [prefix] if isinstance(prefix, str) else prefix
        used = next((each for each in prefixes if each and message.content.startswith(each)), None)
        if used is None or not view.skip_string(used):
            return ctx
        if self.strip_after_prefix:
            view.skip_ws()
        invoker = view.get_word()
        ctx.prefix = used
        ctx.invoked_with = invoker
        ctx.command = (
            lookup_command(self._commands, invoker, case_insensitive=self.case_insensitive)
            if invoker
            else None
        )
        return ctx

    async def invoke(self, ctx: Context, /) -> None:
        """Run the context's command, sending any error to the error handlers."""
        if ctx.command is None:
            if ctx.invoked_with:
                await self.handle_command_error(ctx, CommandNotFoundError(ctx.invoked_with))
            return
        self.dispatch("command", ctx)
        try:
            await ctx.command.invoke(ctx)
        except Exception as error:  # noqa: BLE001 - every error goes to the command error handlers
            ctx.command_failed = True
            await self.handle_command_error(ctx, error)
        else:
            self.dispatch("command_completion", ctx)

    async def process_commands(self, message: Message, /) -> None:
        """Run the command `message` uses, if any; messages from bots are ignored."""
        if message.author.bot:
            return
        ctx = await self.get_context(message)
        if ctx.prefix is None:
            return
        await self.invoke(ctx)

    async def on_message(self, message: Message) -> None:
        """Runs commands; replacing it with `@bot.event` means calling `process_commands` yourself."""
        await self.process_commands(message)

    async def handle_command_error(self, ctx: Context, error: Exception) -> None:
        """Hand `error` to the command's handler, its cog's, then `on_command_error` (as an event)."""
        command = ctx.command
        if command is not None and command.error_handler is not None:
            await _call(command, command.error_handler, ctx, error)
        cog = command.cog if command is not None else None
        if cog is not None and _overrides(cog, "cog_command_error"):
            await cog.cog_command_error(ctx, error)
        self.dispatch("command_error", ctx, error)

    async def on_command_error(self, ctx: Context, error: Exception) -> None:
        """Logs errors no command or cog handler took; replace it with `@bot.event` to report them."""
        command = ctx.command
        if command is not None and (
            command.error_handler is not None
            or (command.cog is not None and _overrides(command.cog, "cog_command_error"))
        ):
            return
        name = command.qualified_name if command is not None else ctx.invoked_with
        _log.error("command %r raised", name, exc_info=error)

    @override
    def __repr__(self) -> str:
        return f"<Bot commands={len(self.commands)} cogs={len(self._cogs)}>"


def _help_command(helper: HelpCommand) -> Command:
    async def help_(ctx: Context, *, command: str | None = None) -> None:
        await helper.command_callback(ctx, command)

    return Command(help_, name=helper.command_name, help="Shows this message")


def _resolve(name: str, package: str | None) -> str:
    try:
        return importlib.util.resolve_name(name, package)
    except ImportError as error:
        raise ExtensionNotFoundError(name) from error


def _overrides(cog: Cog, method: str) -> bool:
    return getattr(type(cog), method) is not getattr(Cog, method)


def _as_listener(method: Callable[..., object]) -> Listener:
    if not inspect.iscoroutinefunction(method):
        msg = f"listener {method!r} must be a coroutine function (async def)"
        raise TypeError(msg)
    return method


async def _call(command: Command, handler: Callable[..., Awaitable[None]], *args: object) -> None:
    parameters = list(inspect.signature(handler).parameters)
    if command.cog is not None and parameters[:1] == ["self"] and not inspect.ismethod(handler):
        await handler(command.cog, *args)
    else:
        await handler(*args)


AutoShardedBot = Bot
"""The same as `Bot`: every bot runs as many shards as Discord recommends, or as it is told."""


def _top_level_slash(command: Command) -> AppCommandBase | AppGroup | None:
    """A hybrid command's slash side, unless it is in a slash group (a `GroupCog`'s) the tree gets."""
    if isinstance(command, HybridCommand | HybridGroup) and command.app_command.parent is None:
        return command.app_command
    return None


def _attach_cog(app_command: AppCommandBase | AppGroup, cog: Cog) -> None:
    """Apply the cog's slash-command check and error handler to one of its slash commands."""
    if _overrides(cog, "interaction_check"):
        app_command.add_check(cog.interaction_check)
    if _overrides(cog, "cog_app_command_error"):
        own = app_command.error_handler

        async def handle(interaction: Interaction, error: Exception) -> None:
            if own is not None:
                await own(interaction, error)
            await cog.cog_app_command_error(interaction, error)

        app_command.error(handle)
