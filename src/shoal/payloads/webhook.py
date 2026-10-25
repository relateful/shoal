"""Webhooks: the message bodies shared by webhook and interaction endpoints.

Discord: https://docs.discord.com/developers/resources/webhook

Not yet modeled: the webhook object and its management endpoints; file uploads, attachments and polls
in message bodies.
"""

from msgspec import UNSET, UnsetType

from shoal.payloads.base import Payload
from shoal.payloads.components import MessageComponent
from shoal.payloads.message import AllowedMentions, Embed, MessageFlags


class EditWebhookMessageParams(Payload):
    """JSON body of Edit Webhook Message, also used to edit interaction responses and follow-ups.

    Every field is optional and nullable: leave one out to keep it, set it to `None` to clear it.

    Discord: https://docs.discord.com/developers/resources/webhook#edit-webhook-message-json/form-params
    """

    content: str | UnsetType | None = UNSET
    embeds: list[Embed] | UnsetType | None = UNSET
    flags: MessageFlags | UnsetType | None = UNSET
    """Only `suppress_embeds` and `is_components_v2` can be changed."""
    allowed_mentions: AllowedMentions | UnsetType | None = UNSET
    components: list[MessageComponent] | UnsetType | None = UNSET
