"""The command tree: registers commands with Discord and runs them when they are used.

    class Bot(shoal.Client):
        def __init__(self) -> None:
            super().__init__(intents=shoal.Intents.default())
            self.tree = app_commands.CommandTree(self)

        async def setup_hook(self) -> None:
            await self.tree.sync()

    bot = Bot()

    @bot.tree.command(description="Say hello")
    async def hello(interaction: Interaction) -> None:
        await interaction.response.send_message(f"Hello, {interaction.user.mention}!")

Discord: https://docs.discord.com/developers/interactions/application-commands
"""

import logging
from collections.abc import Awaitable, Callable, Iterator, Sequence
from typing import Final, override

from msgspec import UnsetType

from shoal.app_commands.commands import (
    AppCommand,
    Command,
    CommandCallback,
    ContextMenu,
    ContextMenuCallback,
    ErrorHandler,
    Group,
)
from shoal.app_commands.errors import (
    AppCommandError,
    CheckFailureError,
    CommandInvokeError,
    CommandNotFoundError,
    TransformerError,
)
from shoal.app_commands.models import AnyChoice, Namespace
from shoal.client.client import Client, ClientError
from shoal.client.interaction import Interaction
from shoal.core.tasks import spawn
from shoal.models.member import Member
from shoal.models.message import Message
from shoal.models.user import User
from shoal.payloads.application_commands import (
    APPLICATION_MAX_COMMANDS,
    OPTION_MAX_CHOICES,
    ApplicationCommand,
    ApplicationCommandOptionType,
    ApplicationCommandType,
)
from shoal.payloads.interactions import (
    ApplicationCommandData,
    ApplicationCommandInteraction,
    ApplicationCommandInteractionDataOption,
    AutocompleteInteraction,
    ResolvedData,
)

type _Key = tuple[str, ApplicationCommandType]

_log = logging.getLogger("shoal.app_commands")

_TARGET: Final = "target"
"""How a context menu's target is named in the errors about it."""
_SUBCOMMANDS: Final = frozenset(
    {ApplicationCommandOptionType.SUB_COMMAND, ApplicationCommandOptionType.SUB_COMMAND_GROUP}
)


def _key(command: AppCommand) -> _Key:
    kind = command.type if isinstance(command, ContextMenu) else ApplicationCommandType.CHAT_INPUT
    return command.name, kind


class CommandTree:
    """The slash commands and context menus of a client, global and per guild.

    Creating a tree hands it the client's command and autocomplete interactions. Commands run in
    their own task, so a slow one never holds up the gateway.

    Discord: https://docs.discord.com/developers/interactions/application-commands
    """

    __slots__ = ("_client", "_error_handler", "_global", "_guilds")

    def __init__(self, client: Client) -> None:
        """A tree for `client`, which then gives it every command interaction."""
        self._client: Client = client
        self._global: dict[_Key, AppCommand] = {}
        self._guilds: dict[int, dict[_Key, AppCommand]] = {}
        self._error_handler: ErrorHandler | None = None
        client.add_interaction_handler(self._handle)

    @property
    def client(self) -> Client:
        """The client the tree belongs to."""
        return self._client

    def _scope(self, guild: int | None) -> dict[_Key, AppCommand]:
        if guild is None:
            return self._global
        return self._guilds.setdefault(guild, {})

    def add_command(
        self,
        command: AppCommand,
        /,
        *,
        guild: int | None = None,
        guilds: Sequence[int] = (),
        override: bool = False,
    ) -> None:
        """Add a command globally, or to `guild` / `guilds` (or those `@guilds` named).

        Raises:
            ValueError: A command of that name and type is already there (pass `override=True` to
                replace it), there are as many as Discord allows, or `command` is a subcommand.
        """
        if not isinstance(command, ContextMenu) and command.parent is not None:
            msg = f"{command.qualified_name!r} belongs to a group; add the group instead"
            raise ValueError(msg)
        targets: list[int | None] = (
            [guild] if guild is not None else list(guilds) or list(command.guild_ids) or [None]
        )
        key = _key(command)
        for target in targets:
            scope = self._scope(target)
            if key in scope and not override:
                msg = f"a {key[1].name} command named {key[0]!r} is already registered"
                raise ValueError(msg)
            if (
                key not in scope
                and sum(1 for _, kind in scope if kind is key[1]) >= APPLICATION_MAX_COMMANDS[key[1]]
            ):
                msg = f"{APPLICATION_MAX_COMMANDS[key[1]]} {key[1].name} commands is the most Discord allows"
                raise ValueError(msg)
        for target in targets:
            self._scope(target)[key] = command

    def remove_command(
        self,
        name: str,
        /,
        *,
        guild: int | None = None,
        type: ApplicationCommandType = ApplicationCommandType.CHAT_INPUT,
    ) -> AppCommand | None:
        """Remove and return the command called `name`, globally or from `guild`."""
        return self._scope(guild).pop((name, type), None)

    def discard(self, command: AppCommand, /) -> None:
        """Remove `command` from every scope it was added to: globally and from each guild."""
        key = _key(command)
        for scope in (self._global, *self._guilds.values()):
            if scope.get(key) is command:
                del scope[key]

    def get_all_commands(self) -> list[AppCommand]:
        """Every command and context menu, global or in any guild, each once."""
        found: dict[int, AppCommand] = {}
        for scope in (self._global, *self._guilds.values()):
            for command in scope.values():
                found.setdefault(id(command), command)
        return list(found.values())

    def get_command(
        self,
        name: str,
        /,
        *,
        guild: int | None = None,
        type: ApplicationCommandType = ApplicationCommandType.CHAT_INPUT,
    ) -> AppCommand | None:
        """The command called `name`, globally or in `guild`."""
        scope = self._global if guild is None else self._guilds.get(guild, {})
        return scope.get((name, type))

    def get_commands(
        self, *, guild: int | None = None, type: ApplicationCommandType | None = None
    ) -> list[AppCommand]:
        """The commands registered globally, or in `guild`; of one `type` if given."""
        scope = self._global if guild is None else self._guilds.get(guild, {})
        return [command for (_, kind), command in scope.items() if type is None or kind is type]

    def walk_commands(self, *, guild: int | None = None) -> Iterator[AppCommand]:
        """Every command, group, subcommand and context menu, globally or in `guild`."""
        for command in self.get_commands(guild=guild):
            yield command
            if isinstance(command, Group):
                yield from command.walk_commands()

    def clear_commands(self, *, guild: int | None) -> None:
        """Remove every command from `guild`, or every global command with `guild=None`."""
        self._scope(guild).clear()

    def copy_global_to(self, *, guild: int) -> None:
        """Register the global commands in `guild` too: they update there instantly while developing.

        Raises:
            ValueError: The guild would hold more commands than Discord allows.
        """
        scope = self._scope(guild)
        merged = {**scope, **self._global}
        for kind, limit in APPLICATION_MAX_COMMANDS.items():
            if sum(1 for _, found in merged if found is kind) > limit:
                msg = f"{limit} {kind.name} commands is the most Discord allows in a guild"
                raise ValueError(msg)
        scope.update(self._global)

    def command(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        nsfw: bool = False,
        guild: int | None = None,
        guilds: Sequence[int] = (),
    ) -> Callable[[CommandCallback], Command]:
        """A decorator that makes a slash command and adds it to the tree."""

        def decorator(callback: CommandCallback) -> Command:
            created = Command(callback=callback, name=name, description=description, nsfw=nsfw)
            self.add_command(created, guild=guild, guilds=guilds)
            return created

        return decorator

    def context_menu(
        self, *, name: str, guild: int | None = None, guilds: Sequence[int] = ()
    ) -> Callable[[ContextMenuCallback], ContextMenu]:
        """A decorator that makes a user or message command and adds it to the tree."""

        def decorator(callback: ContextMenuCallback) -> ContextMenu:
            created = ContextMenu(name=name, callback=callback)
            self.add_command(created, guild=guild, guilds=guilds)
            return created

        return decorator

    async def sync(self, *, guild: int | None = None) -> list[ApplicationCommand]:
        """Replace the app's commands in Discord with the tree's: global ones, or `guild`'s.

        Global changes can take a while to reach every client; guild ones apply at once.

        Raises:
            ClientError: The client has not logged in.

        Discord: https://docs.discord.com/developers/interactions/application-commands#bulk-overwrite-global-application-commands
        """
        application_id = self._client.application_id
        if application_id is None:
            msg = "log in before syncing commands: the application ID is not known yet"
            raise ClientError(msg)
        payloads = [command.to_payload() for command in self.get_commands(guild=guild)]
        commands = self._client.rest.commands
        if guild is None:
            return await commands.overwrite_global(application_id, payloads)
        return await commands.overwrite_guild(application_id, guild, payloads)

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Decide whether any of the tree's commands may run; the default allows them."""
        del interaction
        return True

    def error[F: ErrorHandler](self, handler: F) -> F:
        """Handle the errors commands raise that their own handlers leave; replaces the logging."""
        self._error_handler = handler
        return handler

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        """Called with every error a command raises; logs it unless `error` set a handler."""
        if self._error_handler is not None:
            await self._error_handler(interaction, error)
            return
        command = interaction.command
        name = command.qualified_name if isinstance(command, Command | ContextMenu) else None
        _log.error("command %r raised", name, exc_info=error)

    def _find(self, data: ApplicationCommandData) -> AppCommand | None:
        key = (data.name, data.type)
        if not isinstance(data.guild_id, UnsetType):
            return self._guilds.get(data.guild_id, {}).get(key)
        return self._global.get(key)

    async def _handle(self, interaction: Interaction) -> bool:
        payload = interaction.payload
        if not isinstance(payload, ApplicationCommandInteraction | AutocompleteInteraction):
            return False
        data = payload.data
        found = self._find(data)
        if found is None:
            if isinstance(payload, ApplicationCommandInteraction):
                missing = CommandNotFoundError(data.name)
                _ = spawn(self._report(interaction, None, missing), name=f"shoal-command-{data.name}")
            return False
        resolved = None if isinstance(data.resolved, UnsetType) else data.resolved
        options = [] if isinstance(data.options, UnsetType) else data.options
        if isinstance(payload, AutocompleteInteraction):
            _ = spawn(
                self._autocomplete(interaction, found, options, resolved),
                name=f"shoal-autocomplete-{data.name}",
            )
        else:
            _ = spawn(
                self._run(interaction, found, data, options, resolved), name=f"shoal-command-{data.name}"
            )
        return True

    async def _run(
        self,
        interaction: Interaction,
        found: AppCommand,
        data: ApplicationCommandData,
        options: list[ApplicationCommandInteractionDataOption],
        resolved: ResolvedData | None,
    ) -> None:
        if isinstance(found, ContextMenu):
            interaction.command = found
            try:
                target = _target(interaction, data, resolved)
                await self._check(interaction, found)
                await _invoke(found.name, found.callback(interaction, target))
            except Exception as error:  # noqa: BLE001 - every error a command raises goes to its handlers
                await self._report(interaction, found, error)
            return
        leaf = _resolve(found, options)
        if leaf is None:
            await self._report(
                interaction, None, CommandNotFoundError(" ".join([data.name, *_path(options)]))
            )
            return
        command, leaf_options = leaf
        interaction.command = command
        try:
            arguments = command.arguments(interaction, leaf_options, resolved)
            filled = {option.name for option in leaf_options}
            interaction.namespace = Namespace(
                {
                    item.display_name: arguments[item.name]
                    for item in command.parameters
                    if item.display_name in filled
                }
            )
            await self._check(interaction, command)
            await _invoke(command.qualified_name, command.invoke(interaction, arguments))
        except Exception as error:  # noqa: BLE001 - every error a command raises goes to its handlers
            await self._report(interaction, command, error)

    async def _check(self, interaction: Interaction, command: Command | ContextMenu) -> None:
        if not await self.interaction_check(interaction):
            msg = "the command tree's interaction_check refused the interaction"
            raise CheckFailureError(msg)
        parents: list[Group] = []
        parent = command.parent if isinstance(command, Command) else None
        while parent is not None:
            parents.insert(0, parent)
            parent = parent.parent
        for group in parents:
            if not await group.interaction_check(interaction):
                msg = f"group {group.qualified_name!r} refused the interaction"
                raise CheckFailureError(msg)
            await group.run_checks(interaction)
        await command.run_checks(interaction)

    async def _report(
        self, interaction: Interaction, command: Command | ContextMenu | None, error: Exception
    ) -> None:
        """Hand `error` to the command's handler, its groups' handlers, then the tree's.

        A handler returning `True` handled it: the ones after it, the tree's included, are skipped.
        """
        handlers: list[ErrorHandler] = []
        if command is not None and command.error_handler is not None:
            handlers.append(command.error_handler)
        parent = command.parent if isinstance(command, Command) else None
        while parent is not None:
            if parent.error_handler is not None:
                handlers.append(parent.error_handler)
            parent = parent.parent
        try:
            for handler in handlers:
                if await handler(interaction, error) is True:
                    return
            await self.on_error(interaction, error)
        except Exception:  # noqa: BLE001 - a failing handler must not end the command's task
            _log.exception("an error handler raised while handling %r", error)

    async def _autocomplete(
        self,
        interaction: Interaction,
        found: AppCommand,
        options: list[ApplicationCommandInteractionDataOption],
        resolved: ResolvedData | None,
    ) -> None:
        leaf = _resolve(found, options) if not isinstance(found, ContextMenu) else None
        if leaf is None:
            return
        command, leaf_options = leaf
        interaction.command = command
        focused = next((option for option in leaf_options if option.focused is True), None)
        parameter = command.get_parameter(focused.name) if focused is not None else None
        if focused is None or parameter is None:
            return
        interaction.namespace = Namespace(_lenient(interaction, command, leaf_options, resolved))
        try:
            suggested: Sequence[AnyChoice] = []
            if parameter.autocomplete is not None:
                suggested = await parameter.autocomplete(interaction, str(focused.value))
            await interaction.response.autocomplete(
                [choice.to_payload() for choice in suggested[:OPTION_MAX_CHOICES]]
            )
        except Exception as error:  # noqa: BLE001 - every error an autocomplete raises goes to the handlers
            await self._report(interaction, command, error)

    @override
    def __repr__(self) -> str:
        guild_total = sum(len(scope) for scope in self._guilds.values())
        return f"<CommandTree global={len(self._global)} guild={guild_total}>"


def _path(options: Sequence[ApplicationCommandInteractionDataOption]) -> list[str]:
    """The subcommand group and subcommand names the options pick, outermost first."""
    chosen = next((option for option in options if option.type in _SUBCOMMANDS), None)
    if chosen is None:
        return []
    nested = [] if isinstance(chosen.options, UnsetType) else chosen.options
    return [chosen.name, *_path(nested)]


def _resolve(
    found: Command | Group, options: list[ApplicationCommandInteractionDataOption]
) -> tuple[Command, list[ApplicationCommandInteractionDataOption]] | None:
    """The subcommand the options pick, and its own options."""
    current: Command | Group = found
    while isinstance(current, Group):
        chosen = next((option for option in options if option.type in _SUBCOMMANDS), None)
        child = current.get_command(chosen.name) if chosen is not None else None
        if chosen is None or child is None:
            return None
        current = child
        options = [] if isinstance(chosen.options, UnsetType) else chosen.options
    return current, options


def _lenient(
    interaction: Interaction,
    command: Command,
    options: Sequence[ApplicationCommandInteractionDataOption],
    resolved: ResolvedData | None,
) -> dict[str, object]:
    """The options filled in so far, converted where they can be (autocomplete sees partial input)."""
    values: dict[str, object] = {}
    for option in options:
        parameter = command.get_parameter(option.name)
        if parameter is None or isinstance(option.value, UnsetType):
            continue
        if option.focused is True:
            values[option.name] = option.value
            continue
        try:
            values[option.name] = parameter.convert(interaction, option.value, resolved)
        except TransformerError:
            values[option.name] = option.value
    return values


def _target(
    interaction: Interaction, data: ApplicationCommandData, resolved: ResolvedData | None
) -> User | Member | Message:
    """The user or message a context menu was used on."""
    if isinstance(data.target_id, UnsetType) or resolved is None:
        reason = "Discord did not send the target"
        raise TransformerError(_TARGET, None, reason)
    target_id = data.target_id
    shown = int(target_id)
    state = interaction.state
    if data.type is ApplicationCommandType.MESSAGE:
        message = None if isinstance(resolved.messages, UnsetType) else resolved.messages.get(target_id)
        if message is None:
            reason = "the message was not sent"
            raise TransformerError(_TARGET, shown, reason)
        return Message(state, message, guild_id=interaction.guild_id)
    user = None if isinstance(resolved.users, UnsetType) else resolved.users.get(target_id)
    if user is None:
        reason = "the user was not sent"
        raise TransformerError(_TARGET, shown, reason)
    partial = None if isinstance(resolved.members, UnsetType) else resolved.members.get(target_id)
    if partial is not None and interaction.guild_id is not None:
        return Member.from_partial(state, partial, interaction.guild_id, user=user)
    return User(state, user)


async def _invoke(name: str, running: Awaitable[None]) -> None:
    """Await a callback, wrapping what it raises (other than command errors) in `CommandInvokeError`."""
    try:
        await running
    except AppCommandError:
        raise
    except Exception as error:
        raise CommandInvokeError(name, error) from error
