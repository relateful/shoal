"""Turning `send(...)` keywords into what Discord's endpoints take.

`channel.send`, `message.reply`, `interaction.response.send_message` and `interaction.followup.send`
all accept the same keywords; `outgoing` checks them once and `Outgoing` converts the result into
each endpoint's params.

Discord: https://docs.discord.com/developers/resources/message#create-message
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from msgspec import UNSET, UnsetType

from shoal.core.snowflake import Snowflake
from shoal.models.base import MISSING, MissingType, given, unset_if_none
from shoal.models.embed import Embed
from shoal.models.state import ComponentView
from shoal.payloads.components import ActionRow, MessageComponent
from shoal.payloads.interactions import InteractionMessage, SendFollowupParams
from shoal.payloads.message import (
    AllowedMentions,
    Attachment,
    AttachmentRequest,
    CreateMessageParams,
    EditMessageParams,
    MessageFlags,
    MessageReference,
)
from shoal.payloads.message import Embed as EmbedPayload
from shoal.payloads.poll import PollCreateRequest
from shoal.payloads.webhook import EditWebhookMessageParams
from shoal.rest.files import File

type EmbedLike = Embed | EmbedPayload
"""An embed to send: the builder, or the payload when you already have one."""


def _payload(embed: EmbedLike) -> EmbedPayload:
    return embed.to_payload() if isinstance(embed, Embed) else embed


@dataclass(frozen=True, slots=True)
class Outgoing:
    """A message about to be sent, checked and converted from `send` keywords."""

    content: str | UnsetType = UNSET
    tts: bool | UnsetType = UNSET
    embeds: list[EmbedPayload] | UnsetType = UNSET
    allowed_mentions: AllowedMentions | UnsetType = UNSET
    components: list[MessageComponent] | UnsetType = UNSET
    flags: MessageFlags | UnsetType = UNSET
    poll: PollCreateRequest | UnsetType = UNSET
    files: list[File] = field(default_factory=list[File])
    view: ComponentView | None = None

    def message_params(
        self, *, reference: MessageReference | None = None, sticker_ids: Sequence[int] = ()
    ) -> CreateMessageParams:
        """Create Message's body."""
        return CreateMessageParams(
            content=self.content,
            tts=self.tts,
            embeds=self.embeds,
            allowed_mentions=self.allowed_mentions,
            message_reference=unset_if_none(reference),
            components=self.components,
            sticker_ids=[Snowflake(sticker) for sticker in sticker_ids] if sticker_ids else UNSET,
            flags=self.flags,
            poll=self.poll,
        )

    def interaction_message(self) -> InteractionMessage:
        """The data of a message interaction response."""
        return InteractionMessage(
            tts=self.tts,
            content=self.content,
            embeds=self.embeds,
            allowed_mentions=self.allowed_mentions,
            flags=self.flags,
            components=self.components,
            poll=self.poll,
        )

    def followup_params(self) -> SendFollowupParams:
        """A follow-up message's body."""
        return SendFollowupParams(
            content=self.content,
            tts=self.tts,
            embeds=self.embeds,
            allowed_mentions=self.allowed_mentions,
            components=self.components,
            flags=self.flags,
            poll=self.poll,
        )


def _components_flags(components: list[MessageComponent], flags: MessageFlags) -> MessageFlags:
    """Components other than action rows are Components V2, which Discord requires a flag for."""
    if any(not isinstance(component, ActionRow) for component in components):
        return flags.with_flags(is_components_v2=True)
    return flags


def outgoing(
    content: object = None,
    *,
    tts: bool = False,
    embed: EmbedLike | None = None,
    embeds: Sequence[EmbedLike] | None = None,
    file: File | None = None,
    files: Sequence[File] | None = None,
    allowed_mentions: AllowedMentions | None = None,
    view: ComponentView | None = None,
    suppress_embeds: bool = False,
    silent: bool = False,
    ephemeral: bool = False,
    poll: PollCreateRequest | None = None,
) -> Outgoing:
    """Check `send`'s keywords and build the message.

    `content` is converted with `str()`. `silent` sends without notifying
    (`suppress_notifications`); `ephemeral` only applies to interaction responses.

    Raises:
        TypeError: Both `embed` and `embeds`, or both `file` and `files`, were given.
    """
    if embed is not None and embeds is not None:
        msg = "cannot pass both embed and embeds"
        raise TypeError(msg)
    if file is not None and files is not None:
        msg = "cannot pass both file and files"
        raise TypeError(msg)
    chosen_embeds = [embed] if embed is not None else list(embeds) if embeds is not None else None
    chosen_files = [file] if file is not None else list(files or [])
    flags = MessageFlags(suppress_embeds=suppress_embeds, suppress_notifications=silent, ephemeral=ephemeral)
    components: list[MessageComponent] | UnsetType = UNSET
    if view is not None:
        components = view.to_components()
        flags = _components_flags(components, flags)
    return Outgoing(
        content=UNSET if content is None else str(content),
        tts=tts or UNSET,
        embeds=UNSET if chosen_embeds is None else [_payload(item) for item in chosen_embeds],
        allowed_mentions=UNSET if allowed_mentions is None else allowed_mentions,
        components=components,
        flags=flags if int(flags) else UNSET,
        poll=UNSET if poll is None else poll,
        files=chosen_files,
        view=view,
    )


@dataclass(frozen=True, slots=True)
class Edit:
    """An edit to a message, from `edit(...)`'s keywords."""

    content: str | UnsetType | None = UNSET
    embeds: list[EmbedPayload] | UnsetType | None = UNSET
    allowed_mentions: AllowedMentions | UnsetType | None = UNSET
    components: list[MessageComponent] | UnsetType | None = UNSET
    flags: MessageFlags | UnsetType | None = UNSET
    attachments: list[AttachmentRequest] | UnsetType = UNSET
    """The existing attachments to keep; the request adds an entry for each new file."""
    files: list[File] = field(default_factory=list[File])
    view: ComponentView | None = None

    def message_params(self) -> EditMessageParams:
        """Edit Message's body."""
        return EditMessageParams(
            content=self.content,
            embeds=self.embeds,
            flags=self.flags,
            allowed_mentions=self.allowed_mentions,
            components=self.components,
            attachments=self.attachments,
        )

    def webhook_params(self) -> EditWebhookMessageParams:
        """The body of an edit to a webhook or interaction message."""
        return EditWebhookMessageParams(
            content=self.content,
            embeds=self.embeds,
            flags=self.flags,
            allowed_mentions=self.allowed_mentions,
            components=self.components,
            attachments=self.attachments,
        )

    def interaction_message(self) -> InteractionMessage:
        """The data of an update-message interaction response (fields left out stay as they are)."""
        return InteractionMessage(
            content=_cleared(self.content, ""),
            embeds=_cleared(self.embeds, []),
            allowed_mentions=_cleared(self.allowed_mentions, AllowedMentions()),
            flags=_cleared(self.flags, MessageFlags.none()),
            components=_cleared(self.components, []),
            attachments=self.attachments,
        )


def _cleared[T](value: T | UnsetType | None, empty: T) -> T | UnsetType:
    """`value`, with `None` (clear it) turned into the field's empty value, for bodies without null."""
    return empty if value is None else value


def edit(
    *,
    content: object = MISSING,
    embed: EmbedLike | MissingType | None = MISSING,
    embeds: Sequence[EmbedLike] | MissingType = MISSING,
    attachments: Sequence[File | Attachment] | MissingType = MISSING,
    allowed_mentions: AllowedMentions | MissingType | None = MISSING,
    view: ComponentView | MissingType | None = MISSING,
    suppress: bool | MissingType = MISSING,
    flags: MessageFlags = MessageFlags.none(),  # noqa: B008 - an immutable int
) -> Edit:
    """Check `edit`'s keywords: leave a keyword out to keep that part, pass `None` to clear it.

    `attachments` is every attachment the message keeps: the current ones to keep
    (`message.attachments`) and new `File`s to upload; `[]` removes them all, and leaving it out
    keeps them all. `suppress` hides or shows the link embeds; `flags` are the
    message's current flags, which the edit has to repeat.

    Raises:
        TypeError: Both `embed` and `embeds` were given.
    """
    if not isinstance(embed, MissingType) and not isinstance(embeds, MissingType):
        msg = "cannot pass both embed and embeds"
        raise TypeError(msg)
    new_embeds: list[EmbedPayload] | UnsetType | None = UNSET
    if not isinstance(embed, MissingType):
        new_embeds = None if embed is None else [_payload(embed)]
    elif not isinstance(embeds, MissingType):
        new_embeds = [_payload(item) for item in embeds]
    components: list[MessageComponent] | UnsetType | None = UNSET
    new_flags: MessageFlags | UnsetType = UNSET
    chosen_view = None
    if not isinstance(view, MissingType):
        chosen_view = view
        components = None if view is None else view.to_components()
        if isinstance(components, list) and _components_flags(components, flags) != flags:
            new_flags = _components_flags(components, flags)
    if not isinstance(suppress, MissingType):
        current = new_flags if isinstance(new_flags, MessageFlags) else flags
        new_flags = current.with_flags(suppress_embeds=suppress)
    new_content: str | UnsetType | None = UNSET
    if not isinstance(content, MissingType):
        new_content = None if content is None else str(content)
    return Edit(
        content=new_content,
        embeds=new_embeds,
        allowed_mentions=given(allowed_mentions),
        components=components,
        flags=new_flags,
        attachments=UNSET
        if isinstance(attachments, MissingType)
        else [AttachmentRequest(id=item.id) for item in attachments if isinstance(item, Attachment)],
        files=[]
        if isinstance(attachments, MissingType)
        else [item for item in attachments if isinstance(item, File)],
        view=chosen_view,
    )
