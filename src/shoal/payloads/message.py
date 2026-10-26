"""Messages, embeds, attachments, reactions and the create-message request body.

Discord: https://docs.discord.com/developers/resources/message

Not yet modeled: `Message.application` (a partial application) and `Message.resolved` (resolved
data, which refers back to messages). Decoding ignores those keys until they are added.
"""

from datetime import datetime

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum, DiscordStrEnum
from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.application import ApplicationIntegrationType, InteractionType
from shoal.payloads.base import Payload
from shoal.payloads.channel import Channel, ChannelType, ThreadMember
from shoal.payloads.components import MessageComponent, RawComponent
from shoal.payloads.emoji import Emoji
from shoal.payloads.errors import JSONErrorCode
from shoal.payloads.guild import PartialMember
from shoal.payloads.poll import Poll, PollCreateRequest
from shoal.payloads.sticker import Sticker, StickerItem
from shoal.payloads.user import User


class MessageType(DiscordIntEnum):
    """What produced a message.

    Discord: https://docs.discord.com/developers/resources/message#message-object-message-types
    """

    DEFAULT = 0
    RECIPIENT_ADD = 1
    RECIPIENT_REMOVE = 2
    CALL = 3
    CHANNEL_NAME_CHANGE = 4
    CHANNEL_ICON_CHANGE = 5
    CHANNEL_PINNED_MESSAGE = 6
    USER_JOIN = 7
    GUILD_BOOST = 8
    GUILD_BOOST_TIER_1 = 9
    GUILD_BOOST_TIER_2 = 10
    GUILD_BOOST_TIER_3 = 11
    CHANNEL_FOLLOW_ADD = 12
    GUILD_DISCOVERY_DISQUALIFIED = 14
    GUILD_DISCOVERY_REQUALIFIED = 15
    GUILD_DISCOVERY_GRACE_PERIOD_INITIAL_WARNING = 16
    GUILD_DISCOVERY_GRACE_PERIOD_FINAL_WARNING = 17
    THREAD_CREATED = 18
    REPLY = 19
    CHAT_INPUT_COMMAND = 20
    THREAD_STARTER_MESSAGE = 21
    GUILD_INVITE_REMINDER = 22
    CONTEXT_MENU_COMMAND = 23
    AUTO_MODERATION_ACTION = 24
    ROLE_SUBSCRIPTION_PURCHASE = 25
    INTERACTION_PREMIUM_UPSELL = 26
    STAGE_START = 27
    STAGE_END = 28
    STAGE_SPEAKER = 29
    STAGE_TOPIC = 31
    GUILD_APPLICATION_PREMIUM_SUBSCRIPTION = 32
    GUILD_INCIDENT_ALERT_MODE_ENABLED = 36
    GUILD_INCIDENT_ALERT_MODE_DISABLED = 37
    GUILD_INCIDENT_REPORT_RAID = 38
    GUILD_INCIDENT_REPORT_FALSE_ALARM = 39
    PURCHASE_NOTIFICATION = 44
    POLL_RESULT = 46


class MessageFlags(BaseFlags):
    """Flags on a message.

    Discord: https://docs.discord.com/developers/resources/message#message-object-message-flags
    """

    __slots__ = ()

    crossposted = flag(0)
    is_crosspost = flag(1)
    suppress_embeds = flag(2)
    source_message_deleted = flag(3)
    urgent = flag(4)
    has_thread = flag(5)
    ephemeral = flag(6)
    loading = flag(7)
    failed_to_mention_some_roles_in_thread = flag(8)
    suppress_notifications = flag(12)
    is_voice_message = flag(13)
    has_snapshot = flag(14)
    is_components_v2 = flag(15)


class MessageReferenceType(DiscordIntEnum):
    """Whether a reference is a reply or a forward.

    Discord: https://docs.discord.com/developers/resources/message#message-reference-types
    """

    DEFAULT = 0
    FORWARD = 1


class MessageReference(Payload):
    """Points at another message (replies, forwards, crossposts, pins).

    Discord: https://docs.discord.com/developers/resources/message#message-reference-structure
    """

    type: MessageReferenceType | UnsetType = UNSET
    message_id: Snowflake | UnsetType = UNSET
    channel_id: Snowflake | UnsetType = UNSET
    guild_id: Snowflake | UnsetType = UNSET
    fail_if_not_exists: bool | UnsetType = UNSET


class EmbedType(DiscordStrEnum):
    """How an embed was produced.

    Discord: https://docs.discord.com/developers/resources/message#embed-object-embed-types
    """

    ARTICLE = "article"
    COMPONENTS = "components"
    GIFV = "gifv"
    IMAGE = "image"
    LINK = "link"
    POLL_RESULT = "poll_result"
    RICH = "rich"
    VIDEO = "video"


class EmbedFlags(BaseFlags):
    """Flags on an embed.

    Discord: https://docs.discord.com/developers/resources/message#embed-object-embed-flags
    """

    __slots__ = ()

    is_content_inventory_entry = flag(5)


class EmbedMediaFlags(BaseFlags):
    """Flags on an embed image or video.

    Discord: https://docs.discord.com/developers/resources/message#embed-object-embed-media-flags
    """

    __slots__ = ()

    is_animated = flag(5)


class EmbedFooter(Payload):
    """Embed footer.

    Discord: https://docs.discord.com/developers/resources/message#embed-object-embed-footer-structure
    """

    text: str
    icon_url: str | UnsetType = UNSET
    proxy_icon_url: str | UnsetType = UNSET


class EmbedImage(Payload):
    """An embed image or thumbnail.

    Discord: https://docs.discord.com/developers/resources/message#embed-object-embed-image-structure
    """

    url: str
    proxy_url: str | UnsetType = UNSET
    height: int | UnsetType = UNSET
    width: int | UnsetType = UNSET
    content_type: str | UnsetType = UNSET
    placeholder: str | UnsetType = UNSET
    placeholder_version: int | UnsetType = UNSET
    description: str | UnsetType = UNSET
    flags: EmbedMediaFlags | UnsetType = UNSET


class EmbedVideo(Payload):
    """An embed video.

    Discord: https://docs.discord.com/developers/resources/message#embed-object-embed-video-structure
    """

    url: str | UnsetType = UNSET
    proxy_url: str | UnsetType = UNSET
    height: int | UnsetType = UNSET
    width: int | UnsetType = UNSET
    content_type: str | UnsetType = UNSET
    placeholder: str | UnsetType = UNSET
    placeholder_version: int | UnsetType = UNSET
    description: str | UnsetType = UNSET
    flags: EmbedMediaFlags | UnsetType = UNSET


class EmbedProvider(Payload):
    """The site an embed came from.

    Discord: https://docs.discord.com/developers/resources/message#embed-object-embed-provider-structure
    """

    name: str | UnsetType = UNSET
    url: str | UnsetType = UNSET


class EmbedAuthor(Payload):
    """Embed author line.

    Discord: https://docs.discord.com/developers/resources/message#embed-object-embed-author-structure
    """

    name: str
    url: str | UnsetType = UNSET
    icon_url: str | UnsetType = UNSET
    proxy_icon_url: str | UnsetType = UNSET


class EmbedField(Payload):
    """One embed field.

    Discord: https://docs.discord.com/developers/resources/message#embed-object-embed-field-structure
    """

    name: str
    value: str
    inline: bool | UnsetType = UNSET


class Embed(Payload):
    """Rich content attached to a message.

    Discord: https://docs.discord.com/developers/resources/message#embed-object
    """

    title: str | UnsetType = UNSET
    type: EmbedType | UnsetType = UNSET
    description: str | UnsetType = UNSET
    url: str | UnsetType = UNSET
    timestamp: datetime | UnsetType = UNSET
    color: int | UnsetType = UNSET
    footer: EmbedFooter | UnsetType = UNSET
    image: EmbedImage | UnsetType = UNSET
    thumbnail: EmbedImage | UnsetType = UNSET
    video: EmbedVideo | UnsetType = UNSET
    provider: EmbedProvider | UnsetType = UNSET
    author: EmbedAuthor | UnsetType = UNSET
    fields: list[EmbedField] | UnsetType = UNSET
    flags: EmbedFlags | UnsetType = UNSET


class AttachmentFlags(BaseFlags):
    """Flags on an attachment.

    Discord: https://docs.discord.com/developers/resources/message#attachment-object-attachment-flags
    """

    __slots__ = ()

    is_clip = flag(0)
    is_thumbnail = flag(1)
    is_remix = flag(2)
    is_spoiler = flag(3)
    is_animated = flag(5)


class Attachment(Payload):
    """A file attached to a message.

    Discord: https://docs.discord.com/developers/resources/message#attachment-object
    """

    id: Snowflake
    filename: str
    title: str | UnsetType = UNSET
    description: str | UnsetType = UNSET
    content_type: str | UnsetType = UNSET
    size: int
    url: str
    proxy_url: str
    height: int | UnsetType | None = UNSET
    width: int | UnsetType | None = UNSET
    placeholder: str | UnsetType = UNSET
    placeholder_version: int | UnsetType = UNSET
    ephemeral: bool | UnsetType = UNSET
    duration_secs: float | UnsetType = UNSET
    waveform: str | UnsetType = UNSET
    flags: AttachmentFlags | UnsetType = UNSET
    clip_participants: list[User] | UnsetType = UNSET
    clip_created_at: datetime | UnsetType = UNSET


class AttachmentRequest(Payload):
    """Which attachments a message being created or edited has, and their metadata.

    A new file's `id` is its index `n` in the `files[n]` form field; Shoal fills these in from the
    files passed. To keep an existing attachment when editing, give its ID.

    Discord: https://docs.discord.com/developers/resources/message#attachment-object-attachment-request-structure
    """

    id: int | str
    """The index of a new file, or the ID of an attachment to keep (as a string)."""
    filename: str | UnsetType = UNSET
    title: str | UnsetType = UNSET
    description: str | UnsetType = UNSET
    """Alt text, up to 1024 characters."""
    duration_secs: float | UnsetType = UNSET
    """Required for voice messages."""
    waveform: str | UnsetType = UNSET
    """Base64 sampled waveform; required for voice messages."""
    is_spoiler: bool | UnsetType = UNSET


class ChannelMention(Payload):
    """A channel mentioned in a crossposted message.

    Discord: https://docs.discord.com/developers/resources/message#channel-mention-object
    """

    id: Snowflake
    guild_id: Snowflake
    type: ChannelType
    name: str


class ReactionCountDetails(Payload):
    """Normal and super-reaction counts.

    Discord: https://docs.discord.com/developers/resources/message#reaction-count-details-object
    """

    burst: int
    normal: int


class Reaction(Payload):
    """An emoji reaction on a message.

    Discord: https://docs.discord.com/developers/resources/message#reaction-object
    """

    count: int
    count_details: ReactionCountDetails
    me: bool
    me_burst: bool
    emoji: Emoji
    burst_colors: list[str]


class MessageActivityType(DiscordIntEnum):
    """The Rich Presence action a message invites to.

    Discord: https://docs.discord.com/developers/resources/message#message-object-message-activity-types
    """

    JOIN = 1
    SPECTATE = 2
    LISTEN = 3
    JOIN_REQUEST = 5
    STREAM_REQUEST = 6


class MessageActivity(Payload):
    """A Rich Presence invitation sent in chat.

    Discord: https://docs.discord.com/developers/resources/message#message-object-message-activity-structure
    """

    type: MessageActivityType
    party_id: str | UnsetType = UNSET


class MessageInteractionMetadata(Payload):
    """The interaction a message answers.

    Discord documents one structure per interaction type; their fields are merged here, so an
    interaction type newer than Shoal still decodes. Which fields are set depends on `type`.

    Discord: https://docs.discord.com/developers/resources/message#message-interaction-metadata-object
    """

    id: Snowflake
    type: InteractionType
    user: User
    authorizing_integration_owners: dict[ApplicationIntegrationType, Snowflake]
    original_response_message_id: Snowflake | UnsetType = UNSET
    """Only on follow-up messages."""
    target_user: User | UnsetType = UNSET
    """User commands only."""
    target_message_id: Snowflake | UnsetType = UNSET
    """Message commands only."""
    interacted_message_id: Snowflake | UnsetType = UNSET
    """Components only: the message the component was on."""
    triggering_interaction_metadata: "MessageInteractionMetadata | UnsetType" = UNSET
    """Modal submissions only: the command or component interaction that opened the modal."""


class MessageInteraction(Payload):
    """Deprecated in favour of `Message.interaction_metadata`.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#message-interaction-object
    """

    id: Snowflake
    type: InteractionType
    name: str
    """The command's name, with any subcommand group and subcommand."""
    user: User
    member: PartialMember | UnsetType = UNSET


class MessageCall(Payload):
    """A call in a DM or group DM.

    Discord: https://docs.discord.com/developers/resources/message#message-call-object
    """

    participants: list[Snowflake]
    """User IDs."""
    ended_timestamp: datetime | UnsetType | None = UNSET


class RoleSubscriptionData(Payload):
    """The role subscription purchase or renewal a `ROLE_SUBSCRIPTION_PURCHASE` message is about.

    Discord: https://docs.discord.com/developers/resources/message#role-subscription-data-object
    """

    role_subscription_listing_id: Snowflake
    tier_name: str
    total_months_subscribed: int
    is_renewal: bool


class BaseThemeType(DiscordIntEnum):
    """The mode of a shared client theme.

    Discord: https://docs.discord.com/developers/resources/message#base-theme-types
    """

    UNSET = 0
    """The same as `DARK`."""
    DARK = 1
    LIGHT = 2
    DARKER = 3
    MIDNIGHT = 4


class SharedClientTheme(Payload):
    """A custom client theme shared in a message.

    Discord: https://docs.discord.com/developers/resources/message#shared-client-theme-object
    """

    colors: list[str]
    """Up to 5 hexadecimal colours, such as `5865F2`."""
    gradient_angle: int
    """0 to 360."""
    base_mix: int
    """0 to 100."""
    base_theme: BaseThemeType | UnsetType | None = UNSET


class MessageSnapshotMessage(Payload):
    """The copy of a forwarded message: a few of its fields, as they were when it was forwarded.

    Every field is optional because Discord sends a subset that may change.

    Discord: https://docs.discord.com/developers/resources/message#message-snapshot-object
    """

    type: MessageType | UnsetType = UNSET
    content: str | UnsetType = UNSET
    embeds: list[Embed] | UnsetType = UNSET
    attachments: list[Attachment] | UnsetType = UNSET
    timestamp: datetime | UnsetType = UNSET
    edited_timestamp: datetime | UnsetType | None = UNSET
    flags: MessageFlags | UnsetType = UNSET
    mentions: list[User] | UnsetType = UNSET
    mention_roles: list[Snowflake] | UnsetType = UNSET
    stickers: list[Sticker] | UnsetType = UNSET
    sticker_items: list[StickerItem] | UnsetType = UNSET
    components: list[RawComponent] | UnsetType = UNSET
    """Kept as JSON, like `Message.components`."""


class MessageSnapshot(Payload):
    """A forwarded message, copied when it was forwarded and never updated.

    Discord: https://docs.discord.com/developers/resources/message#message-snapshot-object
    """

    message: MessageSnapshotMessage


class Message(Payload):
    """A message in a channel.

    Discord: https://docs.discord.com/developers/resources/message#message-object
    """

    id: Snowflake
    channel_id: Snowflake
    author: User
    content: str
    timestamp: datetime
    edited_timestamp: datetime | None
    tts: bool
    mention_everyone: bool
    mentions: list[User]
    mention_roles: list[Snowflake]
    mention_channels: list[ChannelMention] | UnsetType = UNSET
    attachments: list[Attachment]
    embeds: list[Embed]
    reactions: list[Reaction] | UnsetType = UNSET
    nonce: int | str | UnsetType = UNSET
    pinned: bool
    webhook_id: Snowflake | UnsetType = UNSET
    type: MessageType
    activity: MessageActivity | UnsetType = UNSET
    application_id: Snowflake | UnsetType = UNSET
    flags: MessageFlags | UnsetType = UNSET
    message_reference: MessageReference | UnsetType = UNSET
    message_snapshots: list[MessageSnapshot] | UnsetType = UNSET
    """Set on forwards: the forwarded message, as it was. Discord sends one at most."""
    referenced_message: "Message | UnsetType | None" = UNSET
    interaction_metadata: MessageInteractionMetadata | UnsetType = UNSET
    interaction: MessageInteraction | UnsetType = UNSET
    """Deprecated; read `interaction_metadata`."""
    thread: Channel | UnsetType = UNSET
    components: list[RawComponent] | UnsetType = UNSET
    """The message's components as Discord sent them; `parse_components` decodes them. Kept as JSON
    so a component type newer than Shoal never stops the message from decoding."""
    sticker_items: list[StickerItem] | UnsetType = UNSET
    stickers: list[Sticker] | UnsetType = UNSET
    """Deprecated; read `sticker_items`."""
    position: int | UnsetType = UNSET
    role_subscription_data: RoleSubscriptionData | UnsetType = UNSET
    poll: Poll | UnsetType = UNSET
    """Absent without the Message Content intent."""
    call: MessageCall | UnsetType = UNSET
    shared_client_theme: SharedClientTheme | UnsetType = UNSET


class AllowedMentionType(DiscordStrEnum):
    """A mention category that `AllowedMentions.parse` can enable.

    Discord: https://docs.discord.com/developers/resources/message#allowed-mentions-object-allowed-mention-types
    """

    EVERYONE = "everyone"
    ROLES = "roles"
    USERS = "users"


class AllowedMentions(Payload):
    """Which mentions in a sent message may notify anyone.

    Discord: https://docs.discord.com/developers/resources/message#allowed-mentions-object
    """

    parse: list[AllowedMentionType] | UnsetType = UNSET
    roles: list[Snowflake] | UnsetType = UNSET
    users: list[Snowflake] | UnsetType = UNSET
    replied_user: bool | UnsetType = UNSET

    @classmethod
    def none(cls) -> "AllowedMentions":
        """Mention nobody, whatever the content says. The safest default for user-supplied text."""
        return cls(parse=[])

    @classmethod
    def all(cls) -> "AllowedMentions":
        """Let every mention in the content notify, including replies."""
        return cls(
            parse=[AllowedMentionType.ROLES, AllowedMentionType.USERS, AllowedMentionType.EVERYONE],
            replied_user=True,
        )


class CreateMessageParams(Payload):
    """JSON body of Create Message.

    Discord: https://docs.discord.com/developers/resources/message#create-message-json/form-params
    """

    content: str | UnsetType = UNSET
    nonce: int | str | UnsetType = UNSET
    tts: bool | UnsetType = UNSET
    embeds: list[Embed] | UnsetType = UNSET
    allowed_mentions: AllowedMentions | UnsetType = UNSET
    message_reference: MessageReference | UnsetType = UNSET
    components: list[MessageComponent] | UnsetType = UNSET
    """Anything but action rows needs `flags=MessageFlags(is_components_v2=True)`, and then
    `content` and `embeds` cannot be used."""
    sticker_ids: list[Snowflake] | UnsetType = UNSET
    attachments: list[AttachmentRequest] | UnsetType = UNSET
    """Filled in from the files passed when left unset."""
    flags: MessageFlags | UnsetType = UNSET
    enforce_nonce: bool | UnsetType = UNSET
    """Return the earlier message instead of sending a duplicate with the same `nonce`."""
    poll: PollCreateRequest | UnsetType = UNSET
    shared_client_theme: SharedClientTheme | UnsetType = UNSET


class ReactionType(DiscordIntEnum):
    """Whether a reaction is a normal or a super (burst) reaction.

    Discord: https://docs.discord.com/developers/resources/message#get-reactions-reaction-types
    """

    NORMAL = 0
    BURST = 1


class SearchAuthorType(DiscordStrEnum):
    """Who sent the messages a search returns. Prefix a value with `-` to exclude it instead.

    Discord: https://docs.discord.com/developers/resources/message#search-guild-messages-author-types
    """

    BOT = "bot"
    USER = "user"
    WEBHOOK = "webhook"


class SearchHasType(DiscordStrEnum):
    """Content a searched message must have. Prefix a value with `-` to exclude it instead.

    Discord: https://docs.discord.com/developers/resources/message#search-guild-messages-search-has-types
    """

    EMBED = "embed"
    FILE = "file"
    IMAGE = "image"
    LINK = "link"
    POLL = "poll"
    SNAPSHOT = "snapshot"
    SOUND = "sound"
    STICKER = "sticker"
    VIDEO = "video"


class SearchEmbedType(DiscordStrEnum):
    """Embed categories a search can filter on (broader than `EmbedType`).

    Discord: https://docs.discord.com/developers/resources/message#search-guild-messages-search-embed-types
    """

    ARTICLE = "article"
    GIF = "gif"
    IMAGE = "image"
    SOUND = "sound"
    VIDEO = "video"


class SearchSortMode(DiscordStrEnum):
    """How search results are ordered.

    Discord: https://docs.discord.com/developers/resources/message#search-guild-messages-search-sort-modes
    """

    RELEVANCE = "relevance"
    TIMESTAMP = "timestamp"


class SearchSortOrder(DiscordStrEnum):
    """Sort direction; ignored when sorting by relevance.

    Discord: https://docs.discord.com/developers/resources/message#search-guild-messages-query-string-params
    """

    ASC = "asc"
    DESC = "desc"


class SearchGuildMessagesParams(Payload):
    """Query of Search Guild Messages. List filters are sent as repeated query parameters.

    The `author_type` and `has` lists take `SearchAuthorType` and `SearchHasType` values; prefix one with
    `-` (see `excluding`) to exclude it instead.

    Discord: https://docs.discord.com/developers/resources/message#search-guild-messages-query-string-params
    """

    limit: int | UnsetType = UNSET
    offset: int | UnsetType = UNSET
    max_id: Snowflake | UnsetType = UNSET
    min_id: Snowflake | UnsetType = UNSET
    slop: int | UnsetType = UNSET
    content: str | UnsetType = UNSET
    channel_id: list[Snowflake] | UnsetType = UNSET
    author_type: list[str] | UnsetType = UNSET
    author_id: list[Snowflake] | UnsetType = UNSET
    mentions: list[Snowflake] | UnsetType = UNSET
    mentions_role_id: list[Snowflake] | UnsetType = UNSET
    mention_everyone: bool | UnsetType = UNSET
    replied_to_user_id: list[Snowflake] | UnsetType = UNSET
    replied_to_message_id: list[Snowflake] | UnsetType = UNSET
    pinned: bool | UnsetType = UNSET
    has: list[str] | UnsetType = UNSET
    embed_type: list[SearchEmbedType] | UnsetType = UNSET
    embed_provider: list[str] | UnsetType = UNSET
    link_hostname: list[str] | UnsetType = UNSET
    attachment_filename: list[str] | UnsetType = UNSET
    attachment_extension: list[str] | UnsetType = UNSET
    sort_by: SearchSortMode | UnsetType = UNSET
    sort_order: SearchSortOrder | UnsetType = UNSET
    include_nsfw: bool | UnsetType = UNSET


def excluding(value: str) -> str:
    """Negate a search filter value: `excluding(SearchHasType.LINK)` matches messages without links.

    Discord: https://docs.discord.com/developers/resources/message#search-guild-messages-search-has-types
    """
    return f"-{value}"


class SearchGuildMessagesResponse(Payload):
    """Response of Search Guild Messages. Messages arrive without their `reactions`.

    `messages` is a list of single-message lists: Discord used to return surrounding context in each
    inner list and keeps the shape. `matches` flattens it.

    Discord: https://docs.discord.com/developers/resources/message#search-guild-messages-response-body
    """

    doing_deep_historical_index: bool
    documents_indexed: int | UnsetType = UNSET
    total_results: int
    messages: list[list[Message]]
    threads: list[Channel] | UnsetType = UNSET
    members: list[ThreadMember] | UnsetType = UNSET

    @property
    def matches(self) -> list[Message]:
        """Every matched message, in order."""
        return [message for group in self.messages for message in group]


class SearchIndexNotReady(Payload):
    """The body of a `202 Accepted` from Search Guild Messages: the guild is not indexed yet.

    Discord: https://docs.discord.com/developers/resources/message#search-guild-messages
    """

    message: str
    code: JSONErrorCode
    documents_indexed: int
    retry_after: float


class GetChannelMessagesParams(Payload):
    """Query of Get Channel Messages. `around`, `before` and `after` are mutually exclusive.

    Discord: https://docs.discord.com/developers/resources/message#get-channel-messages-query-string-params
    """

    around: Snowflake | UnsetType = UNSET
    before: Snowflake | UnsetType = UNSET
    after: Snowflake | UnsetType = UNSET
    limit: int | UnsetType = UNSET
    """1 to 100; Discord's default is 50."""


class GetReactionsParams(Payload):
    """Query of Get Reactions.

    Discord: https://docs.discord.com/developers/resources/message#get-reactions-query-string-params
    """

    type: ReactionType | UnsetType = UNSET
    """Discord's default is `NORMAL`."""
    after: Snowflake | UnsetType = UNSET
    """A user ID."""
    limit: int | UnsetType = UNSET
    """1 to 100; Discord's default is 25."""


class EditMessageParams(Payload):
    """JSON body of Edit Message.

    Other users' messages only allow `flags`. Files passed with the edit are added to the message.
    `attachments`, when given, lists every attachment to keep: existing ones by ID, new files by
    their index. Set it to remove attachments, or to give new files alt text.

    Discord: https://docs.discord.com/developers/resources/message#edit-message-json/form-params
    """

    content: str | UnsetType | None = UNSET
    embeds: list[Embed] | UnsetType | None = UNSET
    flags: MessageFlags | UnsetType | None = UNSET
    """Only `suppress_embeds`, which can be cleared, and `is_components_v2`, which cannot. Include
    the flags already set."""
    allowed_mentions: AllowedMentions | UnsetType | None = UNSET
    components: list[MessageComponent] | UnsetType | None = UNSET
    attachments: list[AttachmentRequest] | UnsetType | None = UNSET


class BulkDeleteMessagesParams(Payload):
    """JSON body of Bulk Delete Messages.

    Discord: https://docs.discord.com/developers/resources/message#bulk-delete-messages-json-params
    """

    messages: list[Snowflake]
    """2 to 100 message IDs, none older than two weeks and none repeated."""


class GetChannelPinsParams(Payload):
    """Query of Get Channel Pins; page with the last pin's `pinned_at` as `before`.

    Discord: https://docs.discord.com/developers/resources/message#get-channel-pins-query-string-params
    """

    before: datetime | UnsetType = UNSET
    limit: int | UnsetType = UNSET
    """1 to 50; Discord's default is 50."""


class MessagePin(Payload):
    """A pinned message and when it was pinned.

    Discord: https://docs.discord.com/developers/resources/message#message-pin-object
    """

    pinned_at: datetime
    message: Message


class ChannelPins(Payload):
    """A page of a channel's pins.

    Discord: https://docs.discord.com/developers/resources/message#get-channel-pins-response-structure
    """

    items: list[MessagePin]
    has_more: bool
