"""Webhook events: what Discord posts to an app's Webhook Events URL.

Discord: https://docs.discord.com/developers/events/webhook-events

Each request is a `WebhookEventPayload`: a `PING` when the URL is saved, or an event whose `data`
stays raw until its type is known. `WEBHOOK_EVENT_PAYLOADS` maps every event type Discord
documents to the type its data decodes into. Not yet modeled: the partial `application` of a game
direct message, as on `Message`.
"""

from datetime import datetime
from typing import Final

from msgspec import UNSET, Raw, UnsetType

from shoal.core.enums import DiscordIntEnum, DiscordStrEnum
from shoal.core.snowflake import Snowflake
from shoal.payloads.application import ApplicationIntegrationType
from shoal.payloads.base import Payload
from shoal.payloads.channel import Channel
from shoal.payloads.components import RawComponent
from shoal.payloads.guild import Guild
from shoal.payloads.message import Attachment, MessageActivity, MessageFlags, MessageType
from shoal.payloads.monetization import Entitlement
from shoal.payloads.user import User


class WebhookPayloadType(DiscordIntEnum):
    """Whether a webhook event request is a `PING` or an event.

    Discord: https://docs.discord.com/developers/events/webhook-events#webhook-types
    """

    PING = 0
    EVENT = 1


class WebhookEventType(DiscordStrEnum):
    """The events an app can subscribe to on its Webhooks settings page.

    Discord: https://docs.discord.com/developers/events/webhook-events#event-types
    """

    APPLICATION_AUTHORIZED = "APPLICATION_AUTHORIZED"
    APPLICATION_DEAUTHORIZED = "APPLICATION_DEAUTHORIZED"
    ENTITLEMENT_CREATE = "ENTITLEMENT_CREATE"
    ENTITLEMENT_DELETE = "ENTITLEMENT_DELETE"
    ENTITLEMENT_UPDATE = "ENTITLEMENT_UPDATE"
    GAME_DIRECT_MESSAGE_CREATE = "GAME_DIRECT_MESSAGE_CREATE"
    GAME_DIRECT_MESSAGE_DELETE = "GAME_DIRECT_MESSAGE_DELETE"
    GAME_DIRECT_MESSAGE_UPDATE = "GAME_DIRECT_MESSAGE_UPDATE"
    LOBBY_MESSAGE_CREATE = "LOBBY_MESSAGE_CREATE"
    LOBBY_MESSAGE_DELETE = "LOBBY_MESSAGE_DELETE"
    LOBBY_MESSAGE_UPDATE = "LOBBY_MESSAGE_UPDATE"
    QUEST_USER_ENROLLMENT = "QUEST_USER_ENROLLMENT"
    """Documented but not sent to apps yet."""


class WebhookEventBody(Payload):
    """The event inside a webhook event request.

    Discord: https://docs.discord.com/developers/events/webhook-events#event-body-object
    """

    type: WebhookEventType
    timestamp: datetime
    data: Raw | UnsetType = UNSET
    """Decode it with the type `WEBHOOK_EVENT_PAYLOADS` gives for `type`."""


class WebhookEventPayload(Payload):
    """A request Discord posts to the Webhook Events URL.

    Discord: https://docs.discord.com/developers/events/webhook-events#payload-structure
    """

    version: int
    application_id: Snowflake
    type: WebhookPayloadType
    event: WebhookEventBody | UnsetType = UNSET


class ApplicationAuthorized(Payload):
    """`APPLICATION_AUTHORIZED`: a user added the app to a server or to their account.

    Discord: https://docs.discord.com/developers/events/webhook-events#application-authorized-application-authorized-structure
    """

    integration_type: ApplicationIntegrationType | UnsetType = UNSET
    user: User
    scopes: list[str]
    guild: Guild | UnsetType = UNSET
    """The server, when the app was added to one (`integration_type` guild)."""


class ApplicationDeauthorized(Payload):
    """`APPLICATION_DEAUTHORIZED`: a user removed the app.

    Discord: https://docs.discord.com/developers/events/webhook-events#application-deauthorized-application-deauthorized-structure
    """

    user: User


class WebhookLobbyMessage(Payload):
    """`LOBBY_MESSAGE_CREATE` and `LOBBY_MESSAGE_UPDATE`: a message in a lobby or a linked channel.

    Discord: https://docs.discord.com/developers/events/webhook-events#lobby-message-object
    """

    id: Snowflake
    type: MessageType
    content: str
    lobby_id: Snowflake
    channel_id: Snowflake
    author: User
    metadata: dict[str, str] | UnsetType = UNSET
    flags: MessageFlags
    application_id: Snowflake | UnsetType = UNSET
    """Present only during an active Social SDK session."""


class LobbyMessageDelete(Payload):
    """`LOBBY_MESSAGE_DELETE`: a message was deleted from a lobby.

    Discord: https://docs.discord.com/developers/events/webhook-events#lobby-message-delete
    """

    id: Snowflake
    lobby_id: Snowflake


class GameDirectMessage(Payload):
    """`GAME_DIRECT_MESSAGE_*`: a direct message during an active Social SDK session.

    Discord sends one of two shapes: a message object with `channel_id` (and, from a linked
    channel, `lobby_id`), or, between two provisional accounts, an in-game message without
    `channel_id` but with `application_id`. Both carry the channel with its recipients.

    Discord: https://docs.discord.com/developers/events/webhook-events#social-sdk-message-objects
    """

    id: Snowflake
    type: MessageType
    content: str
    author: User
    flags: MessageFlags
    channel: Channel
    channel_id: Snowflake | UnsetType = UNSET
    """Set on a message object; absent on an in-game message between provisional accounts."""
    lobby_id: Snowflake | UnsetType = UNSET
    application_id: Snowflake | UnsetType = UNSET
    timestamp: datetime | UnsetType = UNSET
    attachments: list[Attachment] | UnsetType = UNSET
    components: list[RawComponent] | UnsetType = UNSET
    activity: MessageActivity | UnsetType = UNSET

    def is_sdk_message(self) -> bool:
        """Whether it is an in-game message between provisional accounts (no channel ID)."""
        return isinstance(self.channel_id, UnsetType)


WEBHOOK_EVENT_PAYLOADS: Final[dict[WebhookEventType, type[Payload] | None]] = {
    WebhookEventType.APPLICATION_AUTHORIZED: ApplicationAuthorized,
    WebhookEventType.APPLICATION_DEAUTHORIZED: ApplicationDeauthorized,
    WebhookEventType.ENTITLEMENT_CREATE: Entitlement,
    WebhookEventType.ENTITLEMENT_DELETE: Entitlement,
    WebhookEventType.ENTITLEMENT_UPDATE: Entitlement,
    WebhookEventType.GAME_DIRECT_MESSAGE_CREATE: GameDirectMessage,
    WebhookEventType.GAME_DIRECT_MESSAGE_DELETE: GameDirectMessage,
    WebhookEventType.GAME_DIRECT_MESSAGE_UPDATE: GameDirectMessage,
    WebhookEventType.LOBBY_MESSAGE_CREATE: WebhookLobbyMessage,
    WebhookEventType.LOBBY_MESSAGE_DELETE: LobbyMessageDelete,
    WebhookEventType.LOBBY_MESSAGE_UPDATE: WebhookLobbyMessage,
    WebhookEventType.QUEST_USER_ENROLLMENT: None,
}
"""The type each webhook event's `data` decodes into; `None` where Discord documents no shape."""
