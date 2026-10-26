"""Hybrid commands: one definition used both as a prefix command and as a slash command.

    @bot.hybrid_command()
    @app_commands.describe(member="Who to greet")
    async def hello(ctx: commands.Context, member: Member) -> None:
        \"\"\"Say hello to someone.\"\"\"
        await ctx.send(f"Hello, {member.mention}!")

Both ways run the same checks, cooldowns, hooks and callback with a `Context`; errors from either
reach `Bot.on_command_error`. A parameter a slash command cannot express directly (a `Converter`,
a `Message`, an `Emoji`) becomes a text option, converted like the prefix command's argument.
`app_commands` decorators (`describe`, `rename`, `choices`, `autocomplete`, permissions) go below
`@hybrid_command`, on the function.
"""

import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Self, Unpack, override

from shoal.app_commands import commands as app
from shoal.app_commands.parameters import NO_DESCRIPTION, parameter_from_annotation
from shoal.app_commands.parameters import REQUIRED as APP_REQUIRED
from shoal.client.interaction import Interaction
from shoal.commands.core import Command, CommandCallback, CommandOptions, Group, GroupOptions
from shoal.commands.errors import HybridCommandError
from shoal.commands.parameters import NO_DEFAULT, Parameter, has_own_converter
from shoal.payloads.application_commands import COMMAND_DESCRIPTION_MAX_LENGTH


def _slash_annotation(parameter: Parameter) -> tuple[object, bool]:
    """The annotation the slash command uses for `parameter`, and whether it is text to convert.

    A parameter with a converter of its own (`Annotated[str, Shout]`, a `Converter`) is always text
    run through that converter, so both ways of using the command convert it the same.
    """
    as_text = (str | None if parameter.optional else str), True
    if has_own_converter(parameter.annotation):
        return as_text
    default = (
        APP_REQUIRED if parameter.default is NO_DEFAULT and not parameter.optional else parameter.default
    )
    try:
        parameter_from_annotation(parameter.name, parameter.annotation, default)
    except TypeError:
        return as_text
    return parameter.annotation, False


def _app_callback(hybrid: "HybridCommand") -> Callable[..., Awaitable[None]]:
    """A function the slash command calls with the interaction and its options, by name."""
    converted_from_text: set[str] = set()

    async def run(interaction: Interaction, **values: object) -> None:
        await _run_from_interaction(hybrid, interaction, values, converted_from_text)

    signature: list[inspect.Parameter] = [
        inspect.Parameter("interaction", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Interaction)
    ]
    annotations: dict[str, object] = {"interaction": Interaction, "return": None}
    for parameter in hybrid.params:
        if parameter.kind == "every_word" or parameter.greedy:
            msg = f"hybrid command {hybrid.name!r}: *{parameter.name} and Greedy cannot be slash options"
            raise TypeError(msg)
        annotation, as_text = _slash_annotation(parameter)
        if as_text:
            converted_from_text.add(parameter.name)
        annotations[parameter.name] = annotation
        signature.append(
            inspect.Parameter(
                parameter.name,
                inspect.Parameter.KEYWORD_ONLY,
                default=parameter.default,
                annotation=annotation,
            )
        )
    vars(run)["__signature__"] = inspect.Signature(signature)
    run.__annotations__ = annotations
    run.__name__ = hybrid.name
    run.__qualname__ = hybrid.name
    run.__doc__ = hybrid.help
    app.carry_decorators(hybrid.callback, run)
    return run


async def _run_from_interaction(
    hybrid: "HybridCommand", interaction: Interaction, values: Mapping[str, object], as_text: set[str]
) -> None:
    from shoal.commands.bot import Bot

    bot = interaction.client
    if not isinstance(bot, Bot):
        msg = "hybrid commands need a commands.Bot"
        raise TypeError(msg)
    ctx = bot.context_class(bot, interaction, prefix="/")
    parents: list[Group] = []
    parent = hybrid.parent
    while parent is not None:
        parents.insert(0, parent)
        parent = parent.parent
    ctx.invoked_parents = [group.name for group in parents]
    ctx.command = hybrid
    ctx.invoked_with = hybrid.name
    bot.dispatch("command", ctx)
    try:
        # As with `!group sub`: each group's checks and cooldown, then the command's, all before
        # any option is converted (a converter may call Discord). A group's own callback does not
        # run: Discord never invokes a slash group by itself.
        for group in parents:
            ctx.invoked_subcommand = hybrid
            await group.ready(ctx)
        await hybrid.ready(ctx)
        kwargs: dict[str, object] = {}
        for parameter in hybrid.params:
            value = values.get(parameter.name, parameter.fallback)
            if parameter.name in as_text and isinstance(value, str):
                ctx.current_parameter = parameter
                ctx.current_argument = value
                value = await parameter.converter(ctx, value)
            kwargs[parameter.name] = value
        ctx.current_parameter = None
        ctx.kwargs = kwargs
        ctx.command = hybrid
        await hybrid.run(ctx)
    except Exception as error:  # noqa: BLE001 - every error goes to the command error handlers
        ctx.command_failed = True
        await bot.handle_command_error(ctx, error)
    else:
        bot.dispatch("command_completion", ctx)


class HybridCommand(Command):
    """A command used both as `!name ...` and as `/name ...`."""

    __slots__ = ("app_command",)

    def __init__(self, callback: CommandCallback, /, **options: Unpack[CommandOptions]) -> None:
        """A hybrid command running `callback`; keywords as for `Command`.

        Raises:
            TypeError: As for `Command`, or a parameter cannot be a slash option (`*args`, `Greedy`).
            ValueError: The name or description is not one Discord accepts for a slash command.
        """
        super().__init__(callback, **options)
        self.app_command: app.Command = self._build_app_command()

    def _build_app_command(self) -> app.Command:
        description = (self.short_doc or NO_DESCRIPTION)[:COMMAND_DESCRIPTION_MAX_LENGTH]
        command = app.Command(callback=_app_callback(self), name=self.name, description=description)
        command.error(self._slash_error)
        return command

    async def _slash_error(self, interaction: Interaction, error: Exception) -> bool:
        """Send slash-side failures (an option that would not convert, a check) to the command errors.

        They are handled there, so the tree does not report them a second time.
        """
        from shoal.commands.bot import Bot

        bot = interaction.client
        if not isinstance(bot, Bot):
            return False
        ctx = bot.context_class(bot, interaction, prefix="/")
        ctx.command = self
        await bot.handle_command_error(ctx, HybridCommandError(error))
        return True

    @override
    def copy(self) -> Self:
        copied = super().copy()
        rebuilt = copied._build_app_command()  # noqa: SLF001 - the copy is this class's own
        app.copy_settings(self.app_command, rebuilt)
        copied.app_command = rebuilt
        return copied


class HybridGroup(Group):
    """A group used both as `!name sub ...` and as `/name sub ...`.

    Its hybrid subcommands become slash subcommands; plain subcommands stay prefix-only.
    """

    __slots__ = ("app_command",)

    def __init__(self, callback: CommandCallback, /, **options: Unpack[GroupOptions]) -> None:
        """A hybrid group; keywords as for `Group`.

        Raises:
            ValueError: The name or description is not one Discord accepts for a slash command.
        """
        super().__init__(callback, **options)
        description = (self.short_doc or NO_DESCRIPTION)[:COMMAND_DESCRIPTION_MAX_LENGTH]
        self.app_command: app.Group = app.Group(name=self.name, description=description)
        app.apply_group_decorators(callback, self.app_command)

    @override
    def add_command(self, command: Command, /) -> None:
        super().add_command(command)
        if isinstance(command, HybridCommand | HybridGroup):
            self.app_command.add_command(command.app_command)

    @override
    def remove_command(self, name: str, /) -> Command | None:
        removed = super().remove_command(name)
        if isinstance(removed, HybridCommand | HybridGroup):
            self.app_command.remove_command(removed.app_command.name)
        return removed

    def hybrid_command(self, **options: Unpack[CommandOptions]) -> Callable[[CommandCallback], HybridCommand]:
        """A decorator that adds a hybrid subcommand."""

        def decorator(callback: CommandCallback) -> HybridCommand:
            created = HybridCommand(callback, **options)
            self.add_command(created)
            return created

        return decorator

    def hybrid_group(self, **options: Unpack[GroupOptions]) -> Callable[[CommandCallback], "HybridGroup"]:
        """A decorator that adds a hybrid subgroup."""

        def decorator(callback: CommandCallback) -> HybridGroup:
            created = HybridGroup(callback, **options)
            self.add_command(created)
            return created

        return decorator

    @override
    def copy(self) -> Self:
        copied = super().copy()
        copied.app_command = app.Group(name=self.name, description=self.app_command.description)
        app.copy_settings(self.app_command, copied.app_command)
        for command in copied.commands:
            if isinstance(command, HybridCommand | HybridGroup):
                copied.app_command.add_command(command.app_command)
        return copied


def hybrid_command(**options: Unpack[CommandOptions]) -> Callable[[CommandCallback], HybridCommand]:
    """Turn a function into a hybrid command, for a cog or `bot.add_command`."""

    def decorator(callback: CommandCallback) -> HybridCommand:
        return HybridCommand(callback, **options)

    return decorator


def hybrid_group(**options: Unpack[GroupOptions]) -> Callable[[CommandCallback], HybridGroup]:
    """Turn a function into a hybrid group, for a cog or `bot.add_command`."""

    def decorator(callback: CommandCallback) -> HybridGroup:
        return HybridGroup(callback, **options)

    return decorator
