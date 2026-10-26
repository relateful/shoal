"""Webhooks, and the message bodies shared by webhook and interaction endpoints.

Discord: https://docs.discord.com/developers/resources/webhook
"""

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum
from shoal.core.snowflake import Snowflake
from shoal.payloads.api import ImageData
from shoal.payloads.base import Payload
from shoal.payloads.components import MessageComponent
from shoal.payloads.message import AllowedMentions, AttachmentRequest, Embed, MessageFlags
from shoal.payloads.poll import PollCreateRequest
from shoal.payloads.user import User


class WebhookType(DiscordIntEnum):
    """What a webhook is for.

    Discord: https://docs.discord.com/developers/resources/webhook#webhook-object-webhook-types
    """

    INCOMING = 1
    """Posts messages with a generated token."""
    CHANNEL_FOLLOWER = 2
    """Posts an announcement channel's messages into a following channel."""
    APPLICATION = 3
    """Used by interactions."""


class WebhookSourceGuild(Payload):
    """The guild a channel follower webhook copies messages from: a partial guild.

    Discord does not give this object a field table; its fields follow the documented example.

    Discord: https://docs.discord.com/developers/resources/webhook#webhook-object-example-channel-follower-webhook
    """

    id: Snowflake
    name: str
    icon: str | UnsetType | None = UNSET


class WebhookSourceChannel(Payload):
    """The channel a channel follower webhook copies messages from: a partial channel, without type.

    Discord does not give this object a field table; its fields follow the documented example.

    Discord: https://docs.discord.com/developers/resources/webhook#webhook-object-example-channel-follower-webhook
    """

    id: Snowflake
    name: str


class Webhook(Payload):
    """A webhook.

    `token` and `url` are credentials: anyone holding them can post as the webhook. The repr shows
    every field, so log `id` rather than the whole object.

    Discord: https://docs.discord.com/developers/resources/webhook#webhook-object
    """

    REDACTED_FIELDS = frozenset({"token", "url"})

    id: Snowflake
    type: WebhookType
    guild_id: Snowflake | UnsetType | None = UNSET
    channel_id: Snowflake | None
    user: User | UnsetType = UNSET
    """Who created it; not returned when getting a webhook with its token."""
    name: str | None
    avatar: str | None
    token: str | UnsetType = UNSET
    """Only on incoming webhooks."""
    application_id: Snowflake | None
    """The app that created it."""
    source_guild: WebhookSourceGuild | UnsetType = UNSET
    """Channel follower webhooks only, while the creator can still see that guild."""
    source_channel: WebhookSourceChannel | UnsetType = UNSET
    """Channel follower webhooks only, while the creator can still see that guild."""
    url: str | UnsetType = UNSET
    """From the `webhook.incoming` OAuth2 flow."""


class CreateWebhookParams(Payload):
    """JSON body of Create Webhook.

    The name may not contain "clyde" or "discord" and follows the nickname rules, up to 80
    characters.

    Discord: https://docs.discord.com/developers/resources/webhook#create-webhook-json-params
    """

    name: str
    """1 to 80 characters."""
    avatar: ImageData | UnsetType | None = UNSET


class EditWebhookParams(Payload):
    """JSON body of Modify Webhook. Modify Webhook with Token does not take `channel_id`.

    Discord: https://docs.discord.com/developers/resources/webhook#modify-webhook-json-params
    """

    name: str | UnsetType = UNSET
    avatar: ImageData | UnsetType | None = UNSET
    channel_id: Snowflake | UnsetType = UNSET
    """Move the webhook to another channel."""


class EditWebhookWithTokenParams(Payload):
    """JSON body of Modify Webhook with Token, which cannot move the webhook.

    Discord: https://docs.discord.com/developers/resources/webhook#modify-webhook-with-token
    """

    name: str | UnsetType = UNSET
    avatar: ImageData | UnsetType | None = UNSET


class ExecuteWebhookParams(Payload):
    """JSON body of Execute Webhook. Needs content, embeds, components, files or a poll.

    Discord: https://docs.discord.com/developers/resources/webhook#execute-webhook-json/form-params
    """

    content: str | UnsetType = UNSET
    """Up to 2000 characters."""
    username: str | UnsetType = UNSET
    """Overrides the webhook's name for this message."""
    avatar_url: str | UnsetType = UNSET
    """Overrides the webhook's avatar for this message."""
    tts: bool | UnsetType = UNSET
    embeds: list[Embed] | UnsetType = UNSET
    """Up to 10."""
    allowed_mentions: AllowedMentions | UnsetType = UNSET
    components: list[MessageComponent] | UnsetType = UNSET
    """App-owned webhooks can always send them; others only non-interactive ones, with
    `with_components`."""
    attachments: list[AttachmentRequest] | UnsetType = UNSET
    """Filled in from the files passed when left unset."""
    flags: MessageFlags | UnsetType = UNSET
    """Only `suppress_embeds`, `suppress_notifications` and `is_components_v2` can be set."""
    thread_name: str | UnsetType = UNSET
    """In a forum or media channel: create a post with this name."""
    applied_tags: list[Snowflake] | UnsetType = UNSET
    """In a forum or media channel: the new post's tags."""
    poll: PollCreateRequest | UnsetType = UNSET


class EditWebhookMessageParams(Payload):
    """JSON body of Edit Webhook Message, also used to edit interaction responses and follow-ups.

    Every field is optional and nullable: leave one out to keep it, set it to `None` to clear it.
    Files passed with the edit are added; `attachments`, when given, lists every attachment to keep.

    Discord: https://docs.discord.com/developers/resources/webhook#edit-webhook-message-json/form-params
    """

    content: str | UnsetType | None = UNSET
    embeds: list[Embed] | UnsetType | None = UNSET
    flags: MessageFlags | UnsetType | None = UNSET
    """Only `suppress_embeds` and `is_components_v2` can be changed."""
    allowed_mentions: AllowedMentions | UnsetType | None = UNSET
    components: list[MessageComponent] | UnsetType | None = UNSET
    attachments: list[AttachmentRequest] | UnsetType | None = UNSET
    poll: PollCreateRequest | UnsetType | None = UNSET
    """Only when editing a deferred interaction response."""
