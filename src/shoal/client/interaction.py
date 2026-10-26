"""Interactions, answered through `response` and `followup`.

    @client.event
    async def on_interaction(interaction: Interaction) -> None:
        await interaction.response.send_message("Working on it", ephemeral=True)
        await interaction.followup.send("Done!")

Each interaction must be answered once, within three seconds, through `interaction.response`
(`send_message`, `defer`, `edit_message`, `send_modal` or `autocomplete`). After that, and for up
to 15 minutes, `interaction.followup` sends more messages and `edit_original_response` changes the
first one.

Discord: https://docs.discord.com/developers/interactions/receiving-and-responding
"""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final, final, override

from msgspec import UNSET, UnsetType

from shoal.core.errors import ShoalError
from shoal.core.snowflake import Snowflake
from shoal.core.tasks import spawn
from shoal.models.base import MISSING, Hashable, MissingType
from shoal.models.channel import (
    DMChannel,
    MessageableChannel,
    PartialMessageable,
    TextChannel,
    VoiceChannel,
    channel_from_payload,
    resolve_channel,
)
from shoal.models.guild import Guild
from shoal.models.member import Member
from shoal.models.message import Message
from shoal.models.sending import EmbedLike, edit, outgoing
from shoal.models.state import ComponentView, State
from shoal.models.thread import Thread
from shoal.models.user import User
from shoal.payloads.application import InteractionType
from shoal.payloads.application_commands import ApplicationCommandOptionChoice
from shoal.payloads.interactions import (
    INTERACTION_TOKEN_LIFETIME,
    ApplicationCommandInteraction,
    AutocompleteChoices,
    AutocompleteInteraction,
    AutocompleteResponse,
    ComponentInteraction,
    DeferredMessageResponse,
    DeferredUpdateResponse,
    InteractionMessage,
    LaunchActivityResponse,
    MessageResponse,
    ModalResponse,
    ModalSubmitInteraction,
    UpdateMessageResponse,
)
from shoal.payloads.interactions import InteractionResponse as ResponsePayload
from shoal.payloads.message import AllowedMentions, MessageFlags
from shoal.payloads.monetization import Entitlement
from shoal.payloads.permissions import Permissions
from shoal.payloads.poll import PollCreateRequest
from shoal.rest.errors import NotFoundError
from shoal.rest.files import File

if TYPE_CHECKING:
    from shoal.client.client import Client
    from shoal.client.views import SubmittableModal

type InteractionPayload = (
    ApplicationCommandInteraction | ComponentInteraction | AutocompleteInteraction | ModalSubmitInteraction
)
"""Every interaction a bot answers (`PING` is answered by the HTTP server itself)."""

type Responder = Callable[[ResponsePayload, Sequence[File]], Awaitable[None]]
"""Sends the first response: through the callback endpoint, or back through an HTTP reply."""

_COMPONENT_TYPES: Final = frozenset({InteractionType.MESSAGE_COMPONENT, InteractionType.MODAL_SUBMIT})


class InteractionRespondedError(ShoalError):
    """The interaction was already answered; use `interaction.followup` or `edit_original_response`."""

    def __init__(self, interaction: "Interaction") -> None:
        """An error about `interaction`."""
        super().__init__(f"interaction {int(interaction.id)} has already been responded to")
        self.interaction: Interaction = interaction


class Interaction(Hashable):
    """Someone used a command, a component or a modal. Answer it with `response`.

    `command` and `namespace` are set by `app_commands.CommandTree` for the command being run;
    `extras` is free for checks and handlers to share data.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object
    """

    __slots__ = ("_client", "_data", "_state", "command", "extras", "followup", "namespace", "response")

    def __init__(
        self, client: "Client", state: State, data: InteractionPayload, *, responder: Responder | None = None
    ) -> None:
        """An interaction from its payload; `responder` overrides how the first response is sent."""
        self._client: Client = client
        self._state: State = state
        self._data: InteractionPayload = data
        self.response: InteractionResponse = InteractionResponse(self, responder)
        self.followup: Followup = Followup(self)
        self.command: object | None = None
        self.namespace: object | None = None
        self.extras: dict[str, object] = {}

    @property
    @override
    def id(self) -> Snowflake:
        return self._data.id

    @property
    def payload(self) -> InteractionPayload:
        """The interaction as Discord sent it."""
        return self._data

    @property
    def client(self) -> "Client":
        """The client that received it."""
        return self._client

    @property
    def state(self) -> State:
        """The REST client and cache the interaction's models use."""
        return self._state

    @property
    def application_id(self) -> Snowflake:
        """The application it was sent to."""
        return self._data.application_id

    @property
    def type(self) -> InteractionType:
        """Command, component, autocomplete or modal submission."""
        if isinstance(self._data, ApplicationCommandInteraction):
            return InteractionType.APPLICATION_COMMAND
        if isinstance(self._data, ComponentInteraction):
            return InteractionType.MESSAGE_COMPONENT
        if isinstance(self._data, AutocompleteInteraction):
            return InteractionType.APPLICATION_COMMAND_AUTOCOMPLETE
        return InteractionType.MODAL_SUBMIT

    @property
    def token(self) -> str:
        """The token that answers it; valid for 15 minutes. Treat it as a secret."""
        return self._data.token

    @property
    def guild_id(self) -> Snowflake | None:
        """The guild it happened in, or `None` in DMs."""
        guild_id = self._data.guild_id
        return guild_id if isinstance(guild_id, Snowflake) else None

    @property
    def guild(self) -> Guild | None:
        """The guild it happened in, when cached (a user-installed app's guilds usually are not)."""
        return Guild.from_cache(self._state, self.guild_id) if self.guild_id is not None else None

    @property
    def channel_id(self) -> Snowflake | None:
        """The channel it happened in."""
        channel_id = self._data.channel_id
        return channel_id if isinstance(channel_id, Snowflake) else None

    @property
    def channel(self) -> MessageableChannel | None:
        """The channel it happened in: cached, from the interaction, or partial."""
        if self.channel_id is None:
            return None
        cached = resolve_channel(self._state, self.channel_id, self.guild_id)
        sent = self._data.channel
        if isinstance(cached, PartialMessageable) and not isinstance(sent, UnsetType):
            # Not cached (a user-installed app in someone else's guild): use the partial channel sent.
            built = channel_from_payload(self._state, sent)
            if isinstance(built, TextChannel | VoiceChannel | Thread | DMChannel):
                return built
        return cached

    @property
    def user(self) -> User | Member:
        """Who did it: a `Member` in a guild, a `User` elsewhere."""
        member = self._data.member
        if not isinstance(member, UnsetType) and self.guild_id is not None:
            return Member(self._state, member, self.guild_id)
        user = self._data.user
        if isinstance(user, UnsetType):
            msg = "an interaction always has a member or a user"
            raise TypeError(msg)
        return User(self._state, user)

    @property
    def message(self) -> Message | None:
        """For components and modals opened from them: the message the component was on."""
        message = self._data.message
        return (
            None if isinstance(message, UnsetType) else Message(self._state, message, guild_id=self.guild_id)
        )

    @property
    def locale(self) -> str | None:
        """The user's language."""
        locale = self._data.locale
        return None if isinstance(locale, UnsetType) else str(locale)

    @property
    def guild_locale(self) -> str | None:
        """The guild's language."""
        locale = self._data.guild_locale
        return None if isinstance(locale, UnsetType) else str(locale)

    @property
    def permissions(self) -> Permissions:
        """What the user may do where it happened (none known outside guilds)."""
        member = self._data.member
        if isinstance(member, UnsetType) or isinstance(member.permissions, UnsetType):
            return Permissions.none()
        return member.permissions

    @property
    def app_permissions(self) -> Permissions:
        """What the bot may do where it happened."""
        return self._data.app_permissions

    @property
    def entitlements(self) -> list[Entitlement]:
        """The user's entitlements, for monetized apps."""
        return list(self._data.entitlements)

    @property
    @override
    def created_at(self) -> datetime:
        """When it happened."""
        return self.id.created_at

    @property
    def expires_at(self) -> datetime:
        """When its token stops working."""
        return self.created_at + timedelta(seconds=INTERACTION_TOKEN_LIFETIME)

    def is_expired(self) -> bool:
        """Whether its token has stopped working."""
        return datetime.now(self.expires_at.tzinfo) >= self.expires_at

    async def original_response(self) -> Message:
        """The first response message.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#get-original-interaction-response
        """
        data = await self._state.rest.interactions.get_original(self.application_id, self.token)
        return Message(self._state, data, guild_id=self.guild_id)

    async def edit_original_response(
        self,
        *,
        content: object = MISSING,
        embed: EmbedLike | MissingType | None = MISSING,
        embeds: Sequence[EmbedLike] | MissingType = MISSING,
        attachments: Sequence[File] | MissingType = MISSING,
        allowed_mentions: AllowedMentions | MissingType | None = MISSING,
        view: ComponentView | MissingType | None = MISSING,
    ) -> Message:
        """Edit the first response (including filling in a deferred one).

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#edit-original-interaction-response
        """
        changes = edit(
            content=content,
            embed=embed,
            embeds=embeds,
            attachments=attachments,
            allowed_mentions=allowed_mentions,
            view=view,
        )
        data = await self._state.rest.interactions.edit_original(
            self.application_id, self.token, changes.webhook_params(), files=changes.files
        )
        sent = Message(self._state, data, guild_id=self.guild_id)
        if changes.view is not None and changes.view.is_dispatchable():
            self._state.views.store(changes.view, message_id=sent.id)
        return sent

    async def delete_original_response(self) -> None:
        """Delete the first response.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#delete-original-interaction-response
        """
        await self._state.rest.interactions.delete_original(self.application_id, self.token)

    @override
    def __repr__(self) -> str:
        return f"<Interaction id={int(self.id)} type={self.type.name}>"


@final
class InteractionResponse:
    """The first answer to an interaction; only one method may be called, once.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#responding-to-an-interaction
    """

    __slots__ = ("_parent", "_responder", "_type")

    def __init__(self, parent: Interaction, responder: Responder | None) -> None:
        """The response of `parent`; use `interaction.response`."""
        self._parent: Interaction = parent
        self._responder: Responder | None = responder
        self._type: type[ResponsePayload] | None = None

    def is_done(self) -> bool:
        """Whether the interaction has been answered."""
        return self._type is not None

    @property
    def type(self) -> type[ResponsePayload] | None:
        """How it was answered, once it was."""
        return self._type

    async def _send(self, response: ResponsePayload, files: Sequence[File] = ()) -> None:
        if self._type is not None:
            raise InteractionRespondedError(self._parent)
        self._type = type(response)
        parent = self._parent
        if self._responder is not None:
            await self._responder(response, files)
            return
        await parent.state.rest.interactions.respond(parent.id, parent.token, response, files=files)

    def _delete_later(self, delay: float) -> None:
        parent = self._parent

        async def later() -> None:
            await asyncio.sleep(delay)
            with contextlib.suppress(NotFoundError):
                await parent.delete_original_response()

        _ = spawn(later(), name=f"shoal-delete-response-{int(parent.id)}")

    async def send_message(
        self,
        content: object = None,
        *,
        tts: bool = False,
        embed: EmbedLike | None = None,
        embeds: Sequence[EmbedLike] | None = None,
        file: File | None = None,
        files: Sequence[File] | None = None,
        view: ComponentView | None = None,
        ephemeral: bool = False,
        allowed_mentions: AllowedMentions | None = None,
        suppress_embeds: bool = False,
        silent: bool = False,
        delete_after: float | None = None,
        poll: PollCreateRequest | None = None,
    ) -> None:
        """Answer with a message; `ephemeral` shows it only to the user.

        Raises:
            InteractionRespondedError: The interaction was already answered.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#create-interaction-response
        """
        message = outgoing(
            content,
            tts=tts,
            embed=embed,
            embeds=embeds,
            file=file,
            files=files,
            allowed_mentions=allowed_mentions,
            view=view,
            suppress_embeds=suppress_embeds,
            silent=silent,
            ephemeral=ephemeral,
            poll=poll,
        )
        await self._send(MessageResponse(data=message.interaction_message()), message.files)
        state = self._parent.state
        if view is not None and view.is_dispatchable():
            state.views.store(view, message_id=None)
        if delete_after is not None:
            self._delete_later(delete_after)

    async def defer(self, *, ephemeral: bool = False, thinking: bool = False) -> None:
        """Answer later, then fill it in with `edit_original_response` or `followup.send`.

        Commands and modals show "thinking"; components show nothing, unless `thinking` is set.

        Raises:
            InteractionRespondedError: The interaction was already answered.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-interaction-callback-type
        """
        if self._parent.type in _COMPONENT_TYPES and not thinking:
            await self._send(DeferredUpdateResponse())
            return
        flags = MessageFlags(ephemeral=True) if ephemeral else UNSET
        await self._send(DeferredMessageResponse(data=InteractionMessage(flags=flags)))

    async def edit_message(
        self,
        *,
        content: object = MISSING,
        embed: EmbedLike | MissingType | None = MISSING,
        embeds: Sequence[EmbedLike] | MissingType = MISSING,
        attachments: Sequence[File] | MissingType = MISSING,
        view: ComponentView | MissingType | None = MISSING,
        allowed_mentions: AllowedMentions | MissingType | None = MISSING,
        delete_after: float | None = None,
    ) -> None:
        """Answer a component or modal by editing the message it was on.

        Raises:
            InteractionRespondedError: The interaction was already answered.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-interaction-callback-type
        """
        changes = edit(
            content=content,
            embed=embed,
            embeds=embeds,
            attachments=attachments,
            view=view,
            allowed_mentions=allowed_mentions,
        )
        await self._send(UpdateMessageResponse(data=changes.interaction_message()), changes.files)
        message = self._parent.message
        state = self._parent.state
        if changes.view is not None and changes.view.is_dispatchable():
            state.views.store(changes.view, message_id=message.id if message is not None else None)
        if delete_after is not None:
            self._delete_later(delete_after)

    async def send_modal(self, modal: "SubmittableModal", /) -> None:
        """Answer by showing a modal; its submission comes back as a new interaction.

        Raises:
            InteractionRespondedError: The interaction was already answered.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-modal
        """
        await self._send(ModalResponse(data=modal.to_modal()))
        self._parent.client.view_store.store_modal(modal, user_id=self._parent.user.id)

    async def autocomplete(self, choices: Sequence[ApplicationCommandOptionChoice]) -> None:
        """Answer an autocomplete with up to 25 suggestions.

        Raises:
            InteractionRespondedError: The interaction was already answered.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-autocomplete
        """
        await self._send(AutocompleteResponse(data=AutocompleteChoices(choices=list(choices))))

    async def launch_activity(self) -> None:
        """Answer by launching the application's Activity.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-interaction-callback-type
        """
        await self._send(LaunchActivityResponse())


@final
class Followup:
    """More messages after the first response, for 15 minutes.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#followup-messages
    """

    __slots__ = ("_parent",)

    def __init__(self, parent: Interaction) -> None:
        """The follow-ups of `parent`; use `interaction.followup`."""
        self._parent: Interaction = parent

    async def send(
        self,
        content: object = None,
        *,
        tts: bool = False,
        embed: EmbedLike | None = None,
        embeds: Sequence[EmbedLike] | None = None,
        file: File | None = None,
        files: Sequence[File] | None = None,
        view: ComponentView | None = None,
        ephemeral: bool = False,
        allowed_mentions: AllowedMentions | None = None,
        suppress_embeds: bool = False,
        silent: bool = False,
        poll: PollCreateRequest | None = None,
    ) -> Message:
        """Send a follow-up message.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#create-followup-message
        """
        parent = self._parent
        message = outgoing(
            content,
            tts=tts,
            embed=embed,
            embeds=embeds,
            file=file,
            files=files,
            allowed_mentions=allowed_mentions,
            view=view,
            suppress_embeds=suppress_embeds,
            silent=silent,
            ephemeral=ephemeral,
            poll=poll,
        )
        state = parent.state
        data = await state.rest.interactions.send_followup(
            parent.application_id, parent.token, message.followup_params(), files=message.files
        )
        sent = Message(state, data, guild_id=parent.guild_id)
        if view is not None and view.is_dispatchable():
            state.views.store(view, message_id=sent.id)
        return sent

    async def fetch_message(self, message_id: int, /) -> Message:
        """Get a follow-up message.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#get-followup-message
        """
        parent = self._parent
        state = parent.state
        data = await state.rest.interactions.get_followup(parent.application_id, parent.token, message_id)
        return Message(state, data, guild_id=parent.guild_id)

    async def edit_message(
        self,
        message_id: int,
        /,
        *,
        content: object = MISSING,
        embed: EmbedLike | MissingType | None = MISSING,
        embeds: Sequence[EmbedLike] | MissingType = MISSING,
        attachments: Sequence[File] | MissingType = MISSING,
        view: ComponentView | MissingType | None = MISSING,
        allowed_mentions: AllowedMentions | MissingType | None = MISSING,
    ) -> Message:
        """Edit a follow-up message.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#edit-followup-message
        """
        parent = self._parent
        state = parent.state
        changes = edit(
            content=content,
            embed=embed,
            embeds=embeds,
            attachments=attachments,
            view=view,
            allowed_mentions=allowed_mentions,
        )
        data = await state.rest.interactions.edit_followup(
            parent.application_id, parent.token, message_id, changes.webhook_params(), files=changes.files
        )
        if changes.view is not None and changes.view.is_dispatchable():
            state.views.store(changes.view, message_id=message_id)
        return Message(state, data, guild_id=parent.guild_id)

    async def delete_message(self, message_id: int, /) -> None:
        """Delete a follow-up message.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#delete-followup-message
        """
        parent = self._parent
        state = parent.state
        await state.rest.interactions.delete_followup(parent.application_id, parent.token, message_id)
