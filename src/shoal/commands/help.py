"""The help command: `!help`, `!help ban`, `!help Moderation`.

    class EmbedHelp(commands.HelpCommand):
        async def send_bot_help(self, mapping):
            ...  # build an embed from mapping: {cog or None: [commands]}
            await self.get_destination().send(embed=embed)

    bot = commands.Bot(command_prefix="!", help_command=EmbedHelp())

Override the `send_*` methods to change how it looks; `self.context` is the context of the current
use (each use gets its own copy of the help command, so uses never share state).
"""

import copy
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, override

from shoal.commands.core import Command, Group
from shoal.commands.errors import CommandError
from shoal.payloads.message import MESSAGE_CONTENT_MAX_LENGTH

if TYPE_CHECKING:
    from shoal.commands.cog import Cog
    from shoal.commands.context import Context
    from shoal.models.channel import MessageableChannel

type HelpMapping = Mapping["Cog | None", list[Command]]
"""Each cog (`None` for commands outside cogs) and its commands."""


class Paginator:
    """Lines split into pages that each fit a message, between `prefix` and `suffix`.

    paginator = Paginator()  # a code block per page
    for line in lines:
        paginator.add_line(line)
    for page in paginator.pages:
        await channel.send(page)
    """

    __slots__ = ("_count", "_current", "_pages", "linesep", "max_size", "prefix", "suffix")

    def __init__(
        self,
        prefix: str | None = "```",
        suffix: str | None = "```",
        max_size: int = MESSAGE_CONTENT_MAX_LENGTH,
        linesep: str = "\n",
    ) -> None:
        """Pages of at most `max_size` characters, lines joined by `linesep`."""
        self.prefix: str | None = prefix
        self.suffix: str | None = suffix
        self.max_size: int = max_size
        self.linesep: str = linesep
        self._pages: list[str] = []
        self._current: list[str] = []
        self._count: int = 0
        self.clear()

    def clear(self) -> None:
        """Forget every page."""
        self._pages = []
        self._new_page()

    def _new_page(self) -> None:
        self._current = [] if self.prefix is None else [self.prefix]
        self._count = 0 if self.prefix is None else len(self.prefix) + len(self.linesep)

    @property
    def max_line_size(self) -> int:
        """The longest line a page can hold, with its prefix and suffix."""
        return self.max_size - len(self.prefix or "") - len(self.suffix or "") - 2 * len(self.linesep)

    def add_line(self, line: str = "", *, empty: bool = False) -> None:
        """Add a line (and an empty one after it with `empty`), starting a page when this one is full.

        Raises:
            RuntimeError: The line is longer than a page can hold (`max_line_size`).
        """
        if len(line) > self.max_line_size:
            msg = f"a line of {len(line)} characters does not fit a page of {self.max_size}"
            raise RuntimeError(msg)
        if self._count + len(line) + len(self.linesep) > self.max_size - len(self.suffix or ""):
            self.close_page()
        self._current.append(line)
        self._count += len(line) + len(self.linesep)
        if empty:
            self._current.append("")
            self._count += len(self.linesep)

    def close_page(self) -> None:
        """End the current page, whether or not it is full."""
        if self.suffix is not None:
            self._current.append(self.suffix)
        self._pages.append(self.linesep.join(self._current))
        self._new_page()

    @property
    def pages(self) -> list[str]:
        """The pages, the current one included if it holds any line."""
        if len(self._current) > (0 if self.prefix is None else 1):
            closing = [] if self.suffix is None else [self.suffix]
            return [*self._pages, self.linesep.join([*self._current, *closing])]
        return list(self._pages)

    def __len__(self) -> int:
        """The characters in every page so far."""
        return sum(len(page) for page in self._pages) + self._count

    @override
    def __repr__(self) -> str:
        return f"<Paginator pages={len(self.pages)} max_size={self.max_size}>"


class HelpCommand:
    """How `help` answers. Subclass it and override the `send_*` methods."""

    __slots__ = ("__dict__", "_context", "command_name", "show_hidden", "sort_commands", "verify_checks")

    def __init__(
        self,
        *,
        command_name: str = "help",
        show_hidden: bool = False,
        verify_checks: bool = True,
        sort_commands: bool = True,
    ) -> None:
        """A help command; `verify_checks` hides commands the user cannot run."""
        self.command_name: str = command_name
        self.show_hidden: bool = show_hidden
        self.verify_checks: bool = verify_checks
        self.sort_commands: bool = sort_commands
        self._context: Context | None = None

    @property
    def context(self) -> "Context":
        """The context of the current use.

        Raises:
            RuntimeError: Read outside a use of the help command.
        """
        if self._context is None:
            msg = "the help command's context exists only while it runs"
            raise RuntimeError(msg)
        return self._context

    def get_destination(self) -> "MessageableChannel":
        """Where help is sent: the channel it was asked in."""
        return self.context.channel

    async def command_callback(self, ctx: "Context", query: str | None) -> None:
        """Answer `help` (with `query` naming a command, a subcommand or a cog); the bot calls this."""
        helper = copy.copy(self)
        helper._context = ctx  # noqa: SLF001 - the copy is this class's own
        await helper.run(query)

    async def run(self, query: str | None) -> None:
        """Send the page for `query`, or the bot's page."""
        bot = self.context.bot
        if query is None:
            await self.send_bot_help(self.get_bot_mapping())
            return
        cog = bot.get_cog(query)
        if cog is not None:
            await self.send_cog_help(cog)
            return
        first, *rest = query.split()
        found = bot.get_command(first)
        if found is None:
            await self.send_error_message(self.command_not_found(first))
            return
        for word in rest:
            child = found.get_command(word) if isinstance(found, Group) else None
            if child is None:
                await self.send_error_message(self.subcommand_not_found(found, word))
                return
            found = child
        if isinstance(found, Group):
            await self.send_group_help(found)
        else:
            await self.send_command_help(found)

    def get_bot_mapping(self) -> dict["Cog | None", list[Command]]:
        """Each cog's top-level commands, and the commands outside cogs under `None`."""
        bot = self.context.bot
        mapping: dict[Cog | None, list[Command]] = {cog: cog.get_commands() for cog in bot.cogs.values()}
        mapping[None] = [command for command in bot.commands if command.cog is None]
        return mapping

    async def filter_commands(self, commands: Sequence[Command]) -> list[Command]:
        """The commands to show: not hidden (unless `show_hidden`), and runnable when `verify_checks`."""
        shown = [command for command in commands if self.show_hidden or not command.hidden]
        if self.verify_checks:
            runnable: list[Command] = []
            for command in shown:
                try:
                    if await command.can_run(self.context):
                        runnable.append(command)
                except CommandError:
                    continue
            shown = runnable
        return sorted(shown, key=lambda command: command.name) if self.sort_commands else shown

    def get_command_signature(self, command: Command) -> str:
        """How to use `command`: `!ban <member> [days=1]`."""
        aliases = "|".join([command.name, *command.aliases])
        name = f"[{aliases}]" if command.aliases else command.name
        parent = command.full_parent_name
        prefix = self.context.clean_prefix
        invocation = f"{prefix}{parent} {name}" if parent else f"{prefix}{name}"
        return f"{invocation} {command.signature}".rstrip()

    def command_not_found(self, name: str) -> str:
        """The message when no command is called `name`."""
        return f'No command called "{name}" found.'

    def subcommand_not_found(self, command: Command, name: str) -> str:
        """The message when `command` has no subcommand `name` (or has none at all)."""
        if isinstance(command, Group) and command.commands:
            return f'Command "{command.qualified_name}" has no subcommand named {name}'
        return f'Command "{command.qualified_name}" has no subcommands.'

    async def send_error_message(self, error: str) -> None:
        """Send `error` (a command was not found)."""
        await self.get_destination().send(error)

    async def send_bot_help(self, mapping: HelpMapping) -> None:
        """Show every command, by cog."""
        raise NotImplementedError

    async def send_cog_help(self, cog: "Cog") -> None:
        """Show a cog's commands."""
        raise NotImplementedError

    async def send_group_help(self, group: Group) -> None:
        """Show a group and its subcommands."""
        raise NotImplementedError

    async def send_command_help(self, command: Command) -> None:
        """Show one command."""
        raise NotImplementedError


class DefaultHelpCommand(HelpCommand):
    """Plain-text help in a code block, split over messages to fit Discord's length limit."""

    __slots__ = ("no_category", "width")

    def __init__(
        self,
        *,
        command_name: str = "help",
        show_hidden: bool = False,
        verify_checks: bool = True,
        sort_commands: bool = True,
        no_category: str = "No Category",
        width: int = 80,
    ) -> None:
        """The default help; commands outside cogs are listed under `no_category`."""
        super().__init__(
            command_name=command_name,
            show_hidden=show_hidden,
            verify_checks=verify_checks,
            sort_commands=sort_commands,
        )
        self.no_category: str = no_category
        self.width: int = width

    def _lines(self, heading: str, commands: Sequence[Command]) -> list[str]:
        if not commands:
            return []
        longest = max(len(command.name) for command in commands)
        lines = [f"{heading}:"]
        for command in commands:
            entry = f"  {command.name:<{longest}} {command.short_doc}".rstrip()
            lines.append(entry if len(entry) <= self.width else entry[: self.width - 3] + "...")
        return lines

    def _ending(self) -> str:
        ctx = self.context
        name = f"{ctx.clean_prefix}{self.command_name}"
        return (
            f"Type {name} command for more info on a command.\n"
            f"You can also type {name} category for more info on a category."
        )

    async def _send(self, lines: Sequence[str]) -> None:
        await _send_pages(self, Paginator(), lines)

    @override
    async def send_bot_help(self, mapping: HelpMapping) -> None:
        """Every command the user can run, under its cog's name."""
        description = self.context.bot.description
        lines = [description, ""] if description else []
        for cog, commands in _by_category(mapping):
            shown = await self.filter_commands(commands)
            lines.extend(self._lines(cog.qualified_name if cog is not None else self.no_category, shown))
        lines.extend(["", self._ending()])
        await self._send(lines)

    @override
    async def send_cog_help(self, cog: "Cog") -> None:
        """A cog's description and commands."""
        lines = [cog.description, ""] if cog.description else []
        lines.extend(self._lines("Commands", await self.filter_commands(cog.get_commands())))
        lines.extend(["", self._ending()])
        await self._send(lines)

    @override
    async def send_group_help(self, group: Group) -> None:
        """A group's usage, help and subcommands."""
        lines = [self.get_command_signature(group), ""]
        if group.help:
            lines.extend([group.help, ""])
        lines.extend(self._lines("Commands", await self.filter_commands(group.commands)))
        lines.extend(["", self._ending()])
        await self._send(lines)

    @override
    async def send_command_help(self, command: Command) -> None:
        """A command's usage, aliases and help."""
        lines = [self.get_command_signature(command)]
        if command.help:
            lines.extend(["", command.help])
        await self._send(lines)


def _by_category(mapping: HelpMapping) -> list[tuple["Cog | None", list[Command]]]:
    """The categories by cog name, commands outside cogs last."""
    return sorted(
        mapping.items(), key=lambda item: (item[0] is None, item[0].qualified_name if item[0] else "")
    )


async def _send_pages(help_command: HelpCommand, paginator: Paginator, lines: Sequence[str]) -> None:
    """Send `lines` to the help command's destination, a message per page; over-long lines are cut."""
    for line in lines:
        paginator.add_line(line[: paginator.max_line_size])
    destination = help_command.get_destination()
    for page in paginator.pages:
        await destination.send(page)


class MinimalHelpCommand(HelpCommand):
    """Plain help without code blocks: commands listed inline under each category.

    `commands_heading` titles a list of commands, `aliases_heading` a command's aliases, and
    `no_category` holds commands outside cogs.
    """

    __slots__ = ("aliases_heading", "commands_heading", "no_category")

    def __init__(
        self,
        *,
        command_name: str = "help",
        show_hidden: bool = False,
        verify_checks: bool = True,
        sort_commands: bool = True,
        commands_heading: str = "Commands",
        aliases_heading: str = "Aliases:",
        no_category: str = "No Category",
    ) -> None:
        """A minimal help; keywords as for `HelpCommand`, and the headings it writes."""
        super().__init__(
            command_name=command_name,
            show_hidden=show_hidden,
            verify_checks=verify_checks,
            sort_commands=sort_commands,
        )
        self.commands_heading: str = commands_heading
        self.aliases_heading: str = aliases_heading
        self.no_category: str = no_category

    @override
    def get_command_signature(self, command: Command) -> str:
        """How to use `command`, under its name alone: its aliases are listed on their own line."""
        return f"{self.context.clean_prefix}{command.qualified_name} {command.signature}".rstrip()

    def get_opening_note(self) -> str:
        """The line before the bot's or a cog's help."""
        name = f"{self.context.clean_prefix}{self.command_name}"
        return f"Use `{name} [command]` for more info on a command."

    def _inline(self, heading: str, commands: Sequence[Command]) -> list[str]:
        if not commands:
            return []
        return [f"__**{heading}**__", " ".join(f"`{command.name}`" for command in commands)]

    def _detailed(self, commands: Sequence[Command]) -> list[str]:
        if not commands:
            return []
        lines = [f"__**{self.commands_heading}**__"]
        lines.extend(
            f"`{self.context.clean_prefix}{command.qualified_name}`"
            + (f" — {command.short_doc}" if command.short_doc else "")
            for command in commands
        )
        return lines

    async def _send(self, lines: Sequence[str]) -> None:
        await _send_pages(self, Paginator(prefix=None, suffix=None), lines)

    @override
    async def send_bot_help(self, mapping: HelpMapping) -> None:
        """The opening note, then each category's commands on one line."""
        description = self.context.bot.description
        lines = [self.get_opening_note(), ""]
        if description:
            lines[0:0] = [description, ""]
        for cog, commands in _by_category(mapping):
            shown = await self.filter_commands(commands)
            lines.extend(self._inline(cog.qualified_name if cog is not None else self.no_category, shown))
        await self._send(lines)

    @override
    async def send_cog_help(self, cog: "Cog") -> None:
        """A cog's description and its commands with their summaries."""
        lines = [self.get_opening_note(), ""]
        if cog.description:
            lines.extend([cog.description, ""])
        lines.extend(self._detailed(await self.filter_commands(cog.get_commands())))
        await self._send(lines)

    @override
    async def send_group_help(self, group: Group) -> None:
        """A group's usage, help and subcommands."""
        lines = [f"`{self.get_command_signature(group)}`", ""]
        if group.help:
            lines.extend([group.help, ""])
        lines.extend(self._detailed(await self.filter_commands(group.commands)))
        await self._send(lines)

    @override
    async def send_command_help(self, command: Command) -> None:
        """A command's usage, aliases and help."""
        lines = [f"`{self.get_command_signature(command)}`"]
        if command.aliases:
            lines.append(f"**{self.aliases_heading}** {', '.join(command.aliases)}")
        if command.help:
            lines.extend(["", command.help])
        await self._send(lines)
