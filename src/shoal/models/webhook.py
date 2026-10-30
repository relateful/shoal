"""Webhooks you send through, by their URL or ID and token, with or without a bot.

    webhook = Webhook.from_url(url, rest=RestClient(None))
    message = await webhook.send("Deployed", username="CI", wait=True)
    await message.edit(content="Deployed v2")

Sending, editing and deleting messages, and fetching, editing or deleting the webhook itself, need
only its token, so a `RestClient(None)` is enough. Without a token, they go through the bot token.

The token is a credential: anyone holding it can post as the webhook. `repr` leaves it out.

Discord: https://docs.discord.com/developers/resources/webhook
"""

import re
from collections.abc import Sequence
from typing import Final, Self, override

import msgspec
from msgspec import UNSET

from shoal.core.snowflake import Snowflake
from shoal.models.base import MISSING, Hashable, MissingType, Object, given
from shoal.models.embed import Embed
from shoal.models.sending import EmbedLike, edit, outgoing
from shoal.models.state import ComponentView
from shoal.payloads.api import image_data
from shoal.payloads.message import AllowedMentions, Attachment
from shoal.payloads.message import Message as MessagePayload
from shoal.payloads.poll import PollCreateRequest
from shoal.payloads.webhook import EditWebhookParams, EditWebhookWithTokenParams, WebhookType
from shoal.payloads.webhook import Webhook as WebhookPayload
from shoal.rest.client import RestClient
from shoal.rest.files import File

_URL: Final = re.compile(
    r"https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api(?:/v[0-9]+)?/webhooks/"
    r"(?P<id>[0-9]{15,20})/(?P<token>[A-Za-z0-9._-]+)/?"
)


class Webhook(Hashable):
    """A webhook to send through, from `Webhook.from_url(url, rest=rest)` or `Webhook.partial`.

    Discord: https://docs.discord.com/developers/resources/webhook#webhook-object
    """

    __slots__ = ("_data", "_rest")

    def __init__(self, data: WebhookPayload, *, rest: RestClient) -> None:
        """Wrap a webhook payload, such as one `rest.webhooks.get` returned."""
        self._data: WebhookPayload = data
        self._rest: RestClient = rest

    @classmethod
    def partial(cls, webhook_id: int, token: str, *, rest: RestClient) -> Self:
        """A webhook known only by its ID and token; `fetch()` fills in the rest."""
        data = WebhookPayload(
            id=Snowflake(webhook_id),
            type=WebhookType.INCOMING,
            channel_id=None,
            name=None,
            avatar=None,
            application_id=None,
            token=token,
        )
        return cls(data, rest=rest)

    @classmethod
    def from_url(cls, url: str, *, rest: RestClient) -> Self:
        """The webhook a URL such as `https://discord.com/api/webhooks/<id>/<token>` names.

        Raises:
            ValueError: `url` is not a webhook URL.
        """
        match = _URL.fullmatch(url.strip())
        if match is None:
            msg = "not a webhook URL"
            raise ValueError(msg)
        return cls.partial(int(match["id"]), match["token"], rest=rest)

    @property
    @override
    def id(self) -> Snowflake:
        return self._data.id

    @property
    def payload(self) -> WebhookPayload:
        """The webhook as Discord sent it."""
        return self._data

    @property
    def type(self) -> WebhookType:
        """Incoming, channel follower or application."""
        return self._data.type

    @property
    def name(self) -> str | None:
        """Its default name; `None` until fetched for a partial webhook."""
        return self._data.name

    @property
    def channel_id(self) -> Snowflake | None:
        """The channel it posts in; `None` until fetched for a partial webhook."""
        return self._data.channel_id

    @property
    def guild_id(self) -> Snowflake | None:
        """The guild it posts in, when known."""
        return self._data.guild_id or None

    @property
    def token(self) -> str | None:
        """Its token, on incoming webhooks; keep it secret."""
        return self._data.token or None

    @property
    def url(self) -> str | None:
        """The URL to send through, when the token is known; keep it secret."""
        token = self.token
        return None if token is None else f"https://discord.com/api/webhooks/{self.id}/{token}"

    async def fetch(self) -> "Webhook":
        """Get the webhook from Discord, with its token if known, otherwise with the bot token.

        Discord: https://docs.discord.com/developers/resources/webhook#get-webhook-with-token
        """
        token = self.token
        if token is None:
            data = await self._rest.webhooks.get(self.id)
        else:
            data = await self._rest.webhooks.get_with_token(self.id, token)
        if token is not None and not data.token:
            data = _with_token(data, token)
        return Webhook(data, rest=self._rest)

    async def edit(
        self,
        *,
        name: str | MissingType = MISSING,
        avatar: bytes | MissingType | None = MISSING,
        channel: Hashable | MissingType = MISSING,
        reason: str | None = None,
    ) -> "Webhook":
        """Change its default name or avatar (`None` removes it), or move it to another `channel`.

        Moving needs the bot token, so it does not use the webhook's token.

        Discord: https://docs.discord.com/developers/resources/webhook#modify-webhook
        """
        avatar_data = avatar if isinstance(avatar, MissingType) or avatar is None else image_data(avatar)
        token = self.token
        if token is None or not isinstance(channel, MissingType):
            params = EditWebhookParams(
                name=given(name),
                avatar=given(avatar_data),
                channel_id=UNSET if isinstance(channel, MissingType) else channel.id,
            )
            data = await self._rest.webhooks.edit(self.id, params, reason=reason)
        else:
            with_token = EditWebhookWithTokenParams(name=given(name), avatar=given(avatar_data))
            data = await self._rest.webhooks.edit_with_token(self.id, token, with_token)
        if token is not None and not data.token:
            data = _with_token(data, token)
        return Webhook(data, rest=self._rest)

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete the webhook, with its token if known, otherwise with the bot token.

        Discord: https://docs.discord.com/developers/resources/webhook#delete-webhook
        """
        token = self.token
        if token is None:
            await self._rest.webhooks.delete(self.id, reason=reason)
        else:
            await self._rest.webhooks.delete_with_token(self.id, token)

    def _token(self) -> str:
        token = self.token
        if token is None:
            msg = "this webhook has no token: only incoming webhooks can send"
            raise ValueError(msg)
        return token

    async def send(
        self,
        content: object = None,
        *,
        username: str | None = None,
        avatar_url: str | None = None,
        tts: bool = False,
        embed: EmbedLike | None = None,
        embeds: Sequence[EmbedLike] | None = None,
        file: File | None = None,
        files: Sequence[File] | None = None,
        allowed_mentions: AllowedMentions | None = None,
        view: ComponentView | None = None,
        suppress_embeds: bool = False,
        silent: bool = False,
        poll: PollCreateRequest | None = None,
        thread: Hashable | None = None,
        thread_name: str | None = None,
        applied_tags: Sequence[Hashable] = (),
        wait: bool = False,
    ) -> "WebhookMessage | None":
        """Send a message; with `wait`, Discord confirms it and it is returned.

        `username` and `avatar_url` replace the webhook's for this message. `thread` sends in a
        thread of its channel; in a forum or media channel, pass `thread` or `thread_name` (a new
        post, with `applied_tags`). A `view` of a webhook the app does not own can only hold
        components nobody interacts with, such as link buttons.

        Raises:
            ValueError: The webhook has no token.
            TypeError: The keywords conflict, as `channel.send` checks them.

        Discord: https://docs.discord.com/developers/resources/webhook#execute-webhook
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
            poll=poll,
        )
        params = message.webhook_params(
            username=username,
            avatar_url=avatar_url,
            thread_name=thread_name,
            applied_tags=[Snowflake(tag.id) for tag in applied_tags],
        )
        thread_id = None if thread is None else thread.id
        data = await self._rest.webhooks.execute(
            self.id,
            self._token(),
            params,
            wait=wait,
            thread_id=thread_id,
            with_components=view is not None,
            files=message.files,
        )
        return None if data is None else WebhookMessage(self, data, thread_id=thread_id)

    async def fetch_message(self, message_id: int, /, *, thread: Hashable | None = None) -> "WebhookMessage":
        """Get a message the webhook sent; pass its `thread` if it is in one.

        Discord: https://docs.discord.com/developers/resources/webhook#get-webhook-message
        """
        thread_id = None if thread is None else thread.id
        data = await self._rest.webhooks.get_message(self.id, self._token(), message_id, thread_id=thread_id)
        return WebhookMessage(self, data, thread_id=thread_id)

    async def edit_message(
        self,
        message_id: int,
        /,
        *,
        content: object = MISSING,
        embed: EmbedLike | MissingType | None = MISSING,
        embeds: Sequence[EmbedLike] | MissingType = MISSING,
        attachments: Sequence[File | Attachment] | MissingType = MISSING,
        view: ComponentView | MissingType | None = MISSING,
        allowed_mentions: AllowedMentions | MissingType | None = MISSING,
        thread: Hashable | None = None,
    ) -> "WebhookMessage":
        """Edit a message the webhook sent. Leave a keyword out to keep that part, pass `None` to clear it.

        Discord: https://docs.discord.com/developers/resources/webhook#edit-webhook-message
        """
        changes = edit(
            content=content,
            embed=embed,
            embeds=embeds,
            attachments=attachments,
            view=view,
            allowed_mentions=allowed_mentions,
        )
        thread_id = None if thread is None else thread.id
        data = await self._rest.webhooks.edit_message(
            self.id,
            self._token(),
            message_id,
            changes.webhook_params(),
            thread_id=thread_id,
            with_components=changes.view is not None,
            files=changes.files,
        )
        return WebhookMessage(self, data, thread_id=thread_id)

    async def delete_message(self, message_id: int, /, *, thread: Hashable | None = None) -> None:
        """Delete a message the webhook sent.

        Discord: https://docs.discord.com/developers/resources/webhook#delete-webhook-message
        """
        thread_id = None if thread is None else thread.id
        await self._rest.webhooks.delete_message(self.id, self._token(), message_id, thread_id=thread_id)

    @override
    def __repr__(self) -> str:
        return f"<Webhook id={self.id} name={self.name!r}>"


def _with_token(data: WebhookPayload, token: str) -> WebhookPayload:
    """`data` with the token it was fetched with; Discord leaves it out of some answers."""
    return msgspec.structs.replace(data, token=token)


class WebhookMessage(Hashable):
    """A message a webhook sent, which the webhook's token can edit and delete."""

    __slots__ = ("_data", "_thread_id", "webhook")

    def __init__(self, webhook: Webhook, data: MessagePayload, *, thread_id: int | None = None) -> None:
        """A message `webhook` sent; `thread_id` is the thread it is in, if any."""
        self.webhook: Webhook = webhook
        self._data: MessagePayload = data
        self._thread_id: int | None = thread_id

    @property
    @override
    def id(self) -> Snowflake:
        return self._data.id

    @property
    def payload(self) -> MessagePayload:
        """The message as Discord sent it."""
        return self._data

    @property
    def channel_id(self) -> Snowflake:
        """The channel (or thread) it is in."""
        return self._data.channel_id

    @property
    def content(self) -> str:
        """Its text."""
        return self._data.content

    @property
    def embeds(self) -> list[Embed]:
        """Its embeds."""
        return [Embed.from_payload(embed) for embed in self._data.embeds]

    @property
    def attachments(self) -> list[Attachment]:
        """Its files."""
        return self._data.attachments

    async def edit(
        self,
        *,
        content: object = MISSING,
        embed: EmbedLike | MissingType | None = MISSING,
        embeds: Sequence[EmbedLike] | MissingType = MISSING,
        attachments: Sequence[File | Attachment] | MissingType = MISSING,
        view: ComponentView | MissingType | None = MISSING,
        allowed_mentions: AllowedMentions | MissingType | None = MISSING,
    ) -> "WebhookMessage":
        """Edit the message, as `Webhook.edit_message` does."""
        thread = None if self._thread_id is None else Object(self._thread_id)
        return await self.webhook.edit_message(
            self.id,
            content=content,
            embed=embed,
            embeds=embeds,
            attachments=attachments,
            view=view,
            allowed_mentions=allowed_mentions,
            thread=thread,
        )

    async def delete(self) -> None:
        """Delete the message."""
        thread = None if self._thread_id is None else Object(self._thread_id)
        await self.webhook.delete_message(self.id, thread=thread)

    @override
    def __repr__(self) -> str:
        return f"<WebhookMessage id={self.id} webhook={self.webhook.id}>"
