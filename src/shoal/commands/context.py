"""The context a prefix or hybrid command runs in: who used it, where, and how to answer.

    @bot.command()
    async def ping(ctx: commands.Context) -> None:
        await ctx.send("Pong")

A hybrid command used as a slash command gets a context too: `ctx.interaction` is set,
`ctx.message` is `None`, and `ctx.send` answers the interaction (then sends follow-ups).
"""

import contextlib
from collections.abc import AsyncGenerator, Sequence
from typing import TYPE_CHECKING, override

from shoal.client.interaction import Interaction
from shoal.commands.view import StringView
from shoal.models.base import Hashable
from shoal.models.guild import Guild
from shoal.models.member import Member
from shoal.models.message import Message
from shoal.models.messageable import MessageTarget
from shoal.models.sending import EmbedLike
from shoal.models.state import ComponentView, State
from shoal.models.user import ClientUser, User
from shoal.payloads.message import AllowedMentions
from shoal.payloads.poll import PollCreateRequest
from shoal.rest.files import File

if TYPE_CHECKING:
    from shoal.commands.bot import Bot
    from shoal.commands.core import Command
    from shoal.commands.parameters import Parameter
    from shoal.models.channel import MessageableChannel


class Context:
    """Where and by whom a command was used, the command, and its parsed arguments."""

    __slots__ = (
        "__dict__",
        "_source",
        "args",
        "bot",
        "channel",
        "command",
        "command_failed",
        "current_argument",
        "current_parameter",
        "invoked_parents",
        "invoked_subcommand",
        "invoked_with",
        "kwargs",
        "prefix",
        "subcommand_passed",
        "view",
    )

    def __init__(
        self,
        bot: "Bot",
        source: Message | Interaction,
        *,
        prefix: str | None = None,
        view: StringView | None = None,
    ) -> None:
        """The context of a message (`Bot.get_context` builds these) or of a slash command's interaction.

        Raises:
            ValueError: The interaction has no channel, as only a `PING` lacks one.
        """
        channel = source.channel
        if channel is None:
            msg = "an interaction without a channel has no command context"
            raise ValueError(msg)
        self.bot: Bot = bot
        self._source: Message | Interaction = source
        self.channel: MessageableChannel = channel
        self.prefix: str | None = prefix
        self.view: StringView = view or StringView("")
        self.command: Command | None = None
        self.invoked_with: str | None = None
        self.invoked_parents: list[str] = []
        self.invoked_subcommand: Command | None = None
        self.subcommand_passed: str | None = None
        self.command_failed: bool = False
        self.args: list[object] = []
        self.kwargs: dict[str, object] = {}
        self.current_parameter: Parameter | None = None
        self.current_argument: str | None = None

    @property
    def state(self) -> State:
        """The REST client, cache and identity every model uses."""
        return self.bot.state

    @property
    def message(self) -> Message | None:
        """The message that used the command; `None` for a slash command."""
        return self._source if isinstance(self._source, Message) else None

    @property
    def interaction(self) -> Interaction | None:
        """The interaction of a hybrid command used as a slash command; `None` for a message."""
        return self._source if isinstance(self._source, Interaction) else None

    @property
    def author(self) -> User | Member:
        """Who used the command: a `Member` in a guild."""
        source = self._source
        return source.user if isinstance(source, Interaction) else source.author

    @property
    def guild(self) -> Guild | None:
        """The guild it was used in, when cached; `None` in DMs."""
        return self._source.guild

    @property
    def me(self) -> Member | ClientUser | None:
        """The bot: its member in the guild when cached, otherwise its user."""
        member = self.guild.me if self.guild is not None else None
        return member if member is not None else self.bot.user

    @property
    def valid(self) -> bool:
        """Whether the message started with a prefix and named a command."""
        return self.prefix is not None and self.command is not None

    @property
    def clean_prefix(self) -> str:
        """The prefix as people see it: `@Bot ` instead of `<@123> `."""
        if self.prefix is None:
            return ""
        user = self.bot.user
        if user is None:
            return self.prefix
        for mention in (f"<@{int(user.id)}>", f"<@!{int(user.id)}>"):
            if self.prefix.startswith(mention):
                return f"@{user.name}{self.prefix.removeprefix(mention)}"
        return self.prefix

    async def send(
        self,
        content: object = None,
        *,
        tts: bool = False,
        embed: EmbedLike | None = None,
        embeds: Sequence[EmbedLike] | None = None,
        file: File | None = None,
        files: Sequence[File] | None = None,
        stickers: Sequence[int | Hashable] = (),
        delete_after: float | None = None,
        allowed_mentions: AllowedMentions | None = None,
        reference: MessageTarget | None = None,
        mention_author: bool | None = None,
        view: ComponentView | None = None,
        suppress_embeds: bool = False,
        silent: bool = False,
        poll: PollCreateRequest | None = None,
        ephemeral: bool = False,
    ) -> Message:
        """Send a message to the channel; for a slash command, answer it (then send follow-ups).

        `ephemeral` applies to slash commands only; `reference`, `mention_author` and `stickers`
        to messages only.
        """
        if self.interaction is None:
            return await self.channel.send(
                content,
                tts=tts,
                embed=embed,
                embeds=embeds,
                file=file,
                files=files,
                stickers=stickers,
                delete_after=delete_after,
                allowed_mentions=allowed_mentions,
                reference=reference,
                mention_author=mention_author,
                view=view,
                suppress_embeds=suppress_embeds,
                silent=silent,
                poll=poll,
            )
        interaction = self.interaction
        if not interaction.response.is_done():
            await interaction.response.send_message(
                content,
                tts=tts,
                embed=embed,
                embeds=embeds,
                file=file,
                files=files,
                view=view,
                ephemeral=ephemeral,
                allowed_mentions=allowed_mentions,
                suppress_embeds=suppress_embeds,
                silent=silent,
                delete_after=delete_after,
                poll=poll,
            )
            return await interaction.original_response()
        sent = await interaction.followup.send(
            content,
            tts=tts,
            embed=embed,
            embeds=embeds,
            file=file,
            files=files,
            view=view,
            ephemeral=ephemeral,
            allowed_mentions=allowed_mentions,
            suppress_embeds=suppress_embeds,
            silent=silent,
            poll=poll,
        )
        if delete_after is not None:
            sent.delete_later(delete_after)
        return sent

    async def reply(
        self,
        content: object = None,
        *,
        tts: bool = False,
        embed: EmbedLike | None = None,
        embeds: Sequence[EmbedLike] | None = None,
        file: File | None = None,
        files: Sequence[File] | None = None,
        delete_after: float | None = None,
        allowed_mentions: AllowedMentions | None = None,
        mention_author: bool | None = None,
        view: ComponentView | None = None,
        silent: bool = False,
        ephemeral: bool = False,
    ) -> Message:
        """Reply to the command's message; for a slash command, the same as `send`."""
        return await self.send(
            content,
            tts=tts,
            embed=embed,
            embeds=embeds,
            file=file,
            files=files,
            delete_after=delete_after,
            allowed_mentions=allowed_mentions,
            reference=self.message,
            mention_author=mention_author,
            view=view,
            silent=silent,
            ephemeral=ephemeral,
        )

    async def defer(self, *, ephemeral: bool = False) -> None:
        """For a slash command, show "thinking" while the work takes longer than 3 seconds.

        Does nothing for a prefix command, which has no deadline.
        """
        if self.interaction is not None and not self.interaction.response.is_done():
            await self.interaction.response.defer(ephemeral=ephemeral, thinking=True)

    @contextlib.asynccontextmanager
    async def typing(self, *, ephemeral: bool = False) -> AsyncGenerator[None]:
        """`async with ctx.typing():` shows the bot typing; a slash command is deferred instead."""
        if self.interaction is not None:
            await self.defer(ephemeral=ephemeral)
            yield
            return
        async with self.channel.typing():
            yield

    async def invoke(self, command: "Command", /, *args: object, **kwargs: object) -> None:
        """Run another command's callback with these arguments, skipping its checks and parsing."""
        await command.call(self, args, kwargs)

    async def send_help(self, entity: "Command | str | None" = None) -> None:
        """Show the help command's page for the bot, or for one command or cog."""
        await self.bot.send_help(self, entity)

    @override
    def __repr__(self) -> str:
        name = self.command.qualified_name if self.command is not None else None
        return f"<Context command={name!r} author={int(self.author.id)}>"
