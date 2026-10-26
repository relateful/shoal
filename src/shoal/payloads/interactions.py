"""Interactions: what a user did with an app, and how the app answers.

Each interaction type is its own class, tagged by `type`, so its `data` is exactly typed:
`ApplicationCommandInteraction.data` is always `ApplicationCommandData`. `parse_interaction` decodes
any of them from a dispatch or an HTTP request body, and returns `UnknownInteraction` for a type newer
than this version of Shoal instead of failing.

Responses work the same way: one class per callback type, so a modal response cannot carry message
data and a message response cannot forget it.

Discord: https://docs.discord.com/developers/interactions/receiving-and-responding

Not yet modeled: `Interaction.guild` (partial guild). Decoding ignores it until it is added.
"""

from typing import Final

import msgspec
from msgspec import UNSET, UnsetType

from shoal.core.codec import JSONObject, PayloadDecodeError, decode_json
from shoal.core.enums import DiscordIntEnum
from shoal.core.snowflake import Snowflake
from shoal.payloads.api import Locale
from shoal.payloads.application import ApplicationIntegrationType, InteractionContextType, InteractionType
from shoal.payloads.application_commands import (
    ApplicationCommandOptionChoice,
    ApplicationCommandOptionType,
    ApplicationCommandType,
)
from shoal.payloads.base import Payload
from shoal.payloads.channel import Channel
from shoal.payloads.components import ComponentType, MessageComponent, ModalComponent, RawComponent
from shoal.payloads.guild import GuildMember, PartialMember
from shoal.payloads.message import (
    AllowedMentions,
    Attachment,
    AttachmentRequest,
    Embed,
    Message,
    MessageFlags,
)
from shoal.payloads.monetization import Entitlement
from shoal.payloads.permissions import Permissions, Role
from shoal.payloads.poll import PollCreateRequest
from shoal.payloads.user import User


class InteractionCallbackType(DiscordIntEnum):
    """How an app answers an interaction.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-interaction-callback-type
    """

    PONG = 1
    CHANNEL_MESSAGE_WITH_SOURCE = 4
    DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5
    DEFERRED_UPDATE_MESSAGE = 6
    UPDATE_MESSAGE = 7
    APPLICATION_COMMAND_AUTOCOMPLETE_RESULT = 8
    MODAL = 9
    PREMIUM_REQUIRED = 10
    """Deprecated; use a premium button."""
    LAUNCH_ACTIVITY = 12


class ResolvedData(Payload):
    """The users, members, roles, channels, messages and attachments an interaction refers to, by ID.

    A member's user is always included under the same ID.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-resolved-data-structure
    """

    users: dict[Snowflake, User] | UnsetType = UNSET
    members: dict[Snowflake, PartialMember] | UnsetType = UNSET
    roles: dict[Snowflake, Role] | UnsetType = UNSET
    channels: dict[Snowflake, Channel] | UnsetType = UNSET
    """Partial channels: only `id`, `name`, `type`, `permissions`, `parent_id` and a few more."""
    messages: dict[Snowflake, Message] | UnsetType = UNSET
    attachments: dict[Snowflake, Attachment] | UnsetType = UNSET


class ApplicationCommandInteractionDataOption(Payload):
    """One parameter the user filled in, or a subcommand with its own parameters.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-application-command-interaction-data-option-structure
    """

    name: str
    type: ApplicationCommandOptionType
    value: str | int | float | bool | UnsetType = UNSET
    """Set for parameters; users, roles, channels and attachments are given by ID (see `resolved`).
    In autocomplete interactions this is whatever the user has typed so far, always a string."""
    options: "list[ApplicationCommandInteractionDataOption] | UnsetType" = UNSET
    focused: bool | UnsetType = UNSET
    """`True` on the option an autocomplete interaction is asking about."""


class ApplicationCommandData(Payload):
    """The command used and what the user filled in.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-application-command-data-structure
    """

    id: Snowflake
    name: str
    type: ApplicationCommandType
    resolved: ResolvedData | UnsetType = UNSET
    options: list[ApplicationCommandInteractionDataOption] | UnsetType = UNSET
    guild_id: Snowflake | UnsetType = UNSET
    """The guild the command is registered in, for guild commands."""
    target_id: Snowflake | UnsetType = UNSET
    """The user or message a user or message command was used on."""


class MessageComponentData(Payload):
    """The component the user used.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-message-component-data-structure
    """

    custom_id: str
    component_type: ComponentType
    id: int | UnsetType = UNSET
    """The component's `id`. Listed in the components reference rather than in this table
    (https://docs.discord.com/developers/components/reference#anatomy-of-a-component)."""
    values: list[str] | UnsetType = UNSET
    """For selects: the chosen values, as strings (IDs for user, role, mentionable and channel
    selects)."""
    resolved: ResolvedData | UnsetType = UNSET


class ModalSubmitData(Payload):
    """What the user entered in a modal.

    `components` stays as received; `parse_submitted_components` decodes it into `Submitted*` types.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-modal-submit-data-structure
    """

    custom_id: str
    components: list[RawComponent]
    resolved: ResolvedData | UnsetType = UNSET


class _InteractionCommon(Payload):
    """Fields every interaction type except `PING` carries."""

    REDACTED_FIELDS = frozenset({"token"})

    id: Snowflake
    application_id: Snowflake
    guild_id: Snowflake | UnsetType = UNSET
    channel: Channel | UnsetType = UNSET
    """A partial channel."""
    channel_id: Snowflake | UnsetType = UNSET
    member: GuildMember | UnsetType = UNSET
    """The invoking member, with `permissions`, when used in a guild."""
    user: User | UnsetType = UNSET
    """The invoking user, when used outside a guild. In a guild it is `member.user`."""
    token: str
    """Valid for 15 minutes; used to respond and to send follow-ups."""
    version: int
    message: Message | UnsetType = UNSET
    """For components, and modals opened from components: the message the component was on."""
    app_permissions: Permissions
    """What the app may do where the interaction happened."""
    locale: Locale | UnsetType = UNSET
    """The invoking user's language."""
    guild_locale: Locale | UnsetType = UNSET
    entitlements: list[Entitlement]
    """For monetized apps: the invoking user's entitlements."""
    authorizing_integration_owners: dict[ApplicationIntegrationType, Snowflake]
    """For each installation that authorized the interaction: the guild ID (`GUILD_INSTALL`, or `0`
    in the bot's DMs) or the authorizing user's ID (`USER_INSTALL`)."""
    context: InteractionContextType | UnsetType = UNSET
    attachment_size_limit: int
    """Largest attachment the response may carry, in bytes."""


class PingInteraction(Payload, tag=1, tag_field="type"):
    """Discord checking an HTTP interactions endpoint. Only sent over HTTP, never on the gateway.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-interaction-structure
    """

    REDACTED_FIELDS = frozenset({"token"})

    id: Snowflake
    application_id: Snowflake
    token: str
    version: int


class ApplicationCommandInteraction(_InteractionCommon, tag=2, tag_field="type"):
    """A slash, user or message command was used.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-interaction-structure
    """

    data: ApplicationCommandData


class ComponentInteraction(_InteractionCommon, tag=3, tag_field="type"):
    """A button was pressed or a select menu changed.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-interaction-structure
    """

    data: MessageComponentData


class AutocompleteInteraction(_InteractionCommon, tag=4, tag_field="type"):
    """The user is typing in an autocomplete option; answer with suggestions.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-interaction-structure
    """

    data: ApplicationCommandData


class ModalSubmitInteraction(_InteractionCommon, tag=5, tag_field="type"):
    """A modal was submitted.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-interaction-structure
    """

    data: ModalSubmitData


type Interaction = (
    PingInteraction
    | ApplicationCommandInteraction
    | ComponentInteraction
    | AutocompleteInteraction
    | ModalSubmitInteraction
)
"""Any interaction this version of Shoal knows.

Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object
"""


class UnknownInteraction(Payload):
    """An interaction of a type newer than this version of Shoal. `data` is the whole JSON object.

    Its `id` and `token` are still enough to respond.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-interaction-type
    """

    REDACTED_FIELDS = frozenset({"token"})

    id: Snowflake
    application_id: Snowflake
    type: int
    token: str
    data: JSONObject


class _OneInteraction(msgspec.Struct, gc=False):
    value: Interaction


class _AnyObject(msgspec.Struct, gc=False):
    value: JSONObject


_KNOWN_TYPES: Final = frozenset(int(kind) for kind in InteractionType)
"""The interaction types Shoal decodes; a failure on any other type means the type is newer."""


class _InteractionHead(Payload):
    """The fields needed to keep (and answer) an interaction of an unknown type."""

    type: int
    id: Snowflake
    application_id: Snowflake
    token: str


def parse_interaction(
    data: bytes | bytearray | memoryview | msgspec.Raw | str,
) -> Interaction | UnknownInteraction:
    """Decode an interaction from the JSON of an `INTERACTION_CREATE` dispatch or an HTTP request body.

    `DispatchEvent.data` (a `msgspec.Raw`) can be passed as it is.

    Raises:
        PayloadDecodeError: The data is not exactly one interaction object, or a known type is malformed.
    """
    raw = data.encode() if isinstance(data, str) else bytes(data)
    # Decoding the head from the unwrapped bytes first rejects anything that is not exactly one
    # JSON object, which the wrapper below could not: `{...},"value":{...}` would be valid inside it.
    head = decode_json(raw, _InteractionHead)
    # Wrapped in a one-field object so the `Interaction` union decodes through a typed struct.
    boxed = b'{"value":' + raw + b"}"
    try:
        return decode_json(boxed, _OneInteraction).value
    except PayloadDecodeError:
        if head.type in _KNOWN_TYPES:
            raise
        return UnknownInteraction(
            type=head.type,
            id=head.id,
            application_id=head.application_id,
            token=head.token,
            data=decode_json(boxed, _AnyObject).value,
        )


INTERACTION_RESPONSE_DEADLINE: Final = 3.0
"""Seconds Discord waits for the first response before it fails the interaction.

Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#responding-to-an-interaction
"""

INTERACTION_TOKEN_LIFETIME: Final = 15 * 60
"""Seconds an interaction token stays valid for follow-ups and edits, from when the interaction is
received.

Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#followup-messages
"""


class InteractionMessage(Payload):
    """A message sent as an interaction response.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-messages
    """

    tts: bool | UnsetType = UNSET
    content: str | UnsetType = UNSET
    embeds: list[Embed] | UnsetType = UNSET
    """At most 10."""
    allowed_mentions: AllowedMentions | UnsetType = UNSET
    flags: MessageFlags | UnsetType = UNSET
    """Only `suppress_embeds`, `ephemeral`, `is_components_v2`, `suppress_notifications` and
    `is_voice_message` can be set."""
    components: list[MessageComponent] | UnsetType = UNSET
    attachments: list[AttachmentRequest] | UnsetType = UNSET
    """Filled in from the files passed when left unset."""
    poll: PollCreateRequest | UnsetType = UNSET


class AutocompleteChoices(Payload):
    """Suggestions for the option being typed.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-autocomplete
    """

    choices: list[ApplicationCommandOptionChoice]
    """At most 25."""


MODAL_MAX_COMPONENTS: Final = 5
"""The most components (labels and text displays) a modal holds.

Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-modal
"""


class Modal(Payload):
    """A popup form.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-modal
    """

    custom_id: str
    title: str
    """Up to 45 characters."""
    components: list[ModalComponent]
    """One to five."""


class PongResponse(Payload, tag=1, tag_field="type"):
    """Acknowledges a `PingInteraction`.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-interaction-callback-type
    """


class MessageResponse(Payload, tag=4, tag_field="type"):
    """Answers with a message.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-interaction-callback-type
    """

    data: InteractionMessage


class DeferredMessageResponse(Payload, tag=5, tag_field="type"):
    """Shows "thinking…"; edit the original response with the real message later.

    Only `data.flags` is used (for example `ephemeral`).

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-interaction-callback-type
    """

    data: InteractionMessage | UnsetType = UNSET


class DeferredUpdateResponse(Payload, tag=6, tag_field="type"):
    """For components: acknowledges now and edits the component's message later.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-interaction-callback-type
    """


class UpdateMessageResponse(Payload, tag=7, tag_field="type"):
    """For components: edits the message the component is on.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-interaction-callback-type
    """

    data: InteractionMessage


class AutocompleteResponse(Payload, tag=8, tag_field="type"):
    """Answers an autocomplete interaction with suggestions.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-interaction-callback-type
    """

    data: AutocompleteChoices


class ModalResponse(Payload, tag=9, tag_field="type"):
    """Opens a modal. Not available in answer to a modal submission.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-interaction-callback-type
    """

    data: Modal


class LaunchActivityResponse(Payload, tag=12, tag_field="type"):
    """Launches the app's Activity.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-interaction-callback-type
    """


type InteractionResponse = (
    PongResponse
    | MessageResponse
    | DeferredMessageResponse
    | DeferredUpdateResponse
    | UpdateMessageResponse
    | AutocompleteResponse
    | ModalResponse
    | LaunchActivityResponse
)
"""The body of Create Interaction Response.

Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object
"""


class InteractionCallback(Payload):
    """The interaction a response answered.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-callback-interaction-callback-object
    """

    id: Snowflake
    type: InteractionType
    activity_instance_id: str | UnsetType = UNSET
    response_message_id: Snowflake | UnsetType = UNSET
    response_message_loading: bool | UnsetType = UNSET
    response_message_ephemeral: bool | UnsetType = UNSET


class ActivityInstanceResource(Payload):
    """The Activity a response launched.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-callback-interaction-callback-activity-instance-resource
    """

    id: str


class InteractionCallbackResource(Payload):
    """What a response created.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-callback-interaction-callback-resource-object
    """

    type: InteractionCallbackType
    activity_instance: ActivityInstanceResource | UnsetType = UNSET
    message: Message | UnsetType = UNSET


class InteractionCallbackResponse(Payload):
    """What Create Interaction Response returns with `with_response=True`.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-callback-interaction-callback-response-object
    """

    interaction: InteractionCallback
    resource: InteractionCallbackResource | UnsetType = UNSET


class SendFollowupParams(Payload):
    """JSON body of Create Followup Message.

    It is Execute Webhook's body without `username`, `avatar_url` and `thread_id`, which follow-ups
    do not support.

    Discord: https://docs.discord.com/developers/resources/webhook#execute-webhook-json/form-params
    """

    content: str | UnsetType = UNSET
    tts: bool | UnsetType = UNSET
    embeds: list[Embed] | UnsetType = UNSET
    allowed_mentions: AllowedMentions | UnsetType = UNSET
    components: list[MessageComponent] | UnsetType = UNSET
    attachments: list[AttachmentRequest] | UnsetType = UNSET
    """Filled in from the files passed when left unset."""
    flags: MessageFlags | UnsetType = UNSET
    """`ephemeral` makes the follow-up visible only to the invoking user."""
    thread_name: str | UnsetType = UNSET
    applied_tags: list[Snowflake] | UnsetType = UNSET
    poll: PollCreateRequest | UnsetType = UNSET
