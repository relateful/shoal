"""Channels, threads and permission overwrites.

Discord: https://docs.discord.com/developers/resources/channel

**Obfuscated channels.** From November 16, 2026 the gateway sends channels the bot cannot view with
their metadata obfuscated: `name` becomes a placeholder, other sensitive fields are nulled, and
`permission_overwrites` holds one fake overwrite denying `VIEW_CHANNEL` to `@everyone`. Only `id`,
`type`, `position` and `parent_id` are trustworthy. Check `Channel.is_obfuscated` (the
`CHANNEL_OBFUSCATED` flag, the only reliable signal) before reading anything else, and use
`Channel.visible_name` rather than `name` for display. When the bot regains access Discord sends a
`CHANNEL_UPDATE` with the full data.
(https://docs.discord.com/developers/resources/channel#channel-object-obfuscated-channels)

"""

from datetime import datetime
from typing import Final

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum
from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.api import ImageData
from shoal.payloads.base import Payload
from shoal.payloads.guild import GuildMember
from shoal.payloads.permissions import Permissions
from shoal.payloads.user import User


class ChannelType(DiscordIntEnum):
    """The kind of channel.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object-channel-types
    """

    GUILD_TEXT = 0
    DM = 1
    GUILD_VOICE = 2
    GROUP_DM = 3
    GUILD_CATEGORY = 4
    GUILD_ANNOUNCEMENT = 5
    ANNOUNCEMENT_THREAD = 10
    PUBLIC_THREAD = 11
    PRIVATE_THREAD = 12
    GUILD_STAGE_VOICE = 13
    GUILD_DIRECTORY = 14
    GUILD_FORUM = 15
    GUILD_MEDIA = 16

    @property
    def is_thread(self) -> bool:
        """Whether this type is one of the three thread types."""
        return self in {
            ChannelType.ANNOUNCEMENT_THREAD,
            ChannelType.PUBLIC_THREAD,
            ChannelType.PRIVATE_THREAD,
        }


class VideoQualityMode(DiscordIntEnum):
    """Camera quality in a voice channel.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object-video-quality-modes
    """

    AUTO = 1
    FULL = 2


class SortOrderType(DiscordIntEnum):
    """How a forum or media channel orders its posts.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object-sort-order-types
    """

    LATEST_ACTIVITY = 0
    CREATION_DATE = 1
    """Newest first."""


class ForumLayoutType(DiscordIntEnum):
    """How a forum channel shows its posts.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object-forum-layout-types
    """

    NOT_SET = 0
    LIST_VIEW = 1
    GALLERY_VIEW = 2


class ChannelFlags(BaseFlags):
    """Flags on a channel.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object-channel-flags
    """

    __slots__ = ()

    pinned = flag(1)
    require_tag = flag(4)
    hide_media_download_options = flag(15)
    channel_obfuscated = flag(17)
    is_spoiler_channel = flag(21)


class OverwriteType(DiscordIntEnum):
    """Whether an overwrite targets a role or a member.

    Discord: https://docs.discord.com/developers/resources/channel#overwrite-object-overwrite-structure
    """

    ROLE = 0
    MEMBER = 1


class Overwrite(Payload):
    """A permission overwrite on a channel.

    Discord: https://docs.discord.com/developers/resources/channel#overwrite-object
    """

    id: Snowflake
    type: OverwriteType
    allow: Permissions
    deny: Permissions


class DefaultReaction(Payload):
    """The emoji on a forum or media post's add-reaction button. Exactly one field is set.

    Discord: https://docs.discord.com/developers/resources/channel#default-reaction-object
    """

    emoji_id: Snowflake | None
    """A guild's custom emoji."""
    emoji_name: str | None
    """A unicode emoji."""


class ForumTag(Payload):
    """A tag that can be applied to posts in a forum or media channel.

    Discord: https://docs.discord.com/developers/resources/channel#forum-tag-object
    """

    id: Snowflake
    name: str
    """0 to 20 characters."""
    moderated: bool
    """Only members with Manage Threads can add or remove it."""
    emoji_id: Snowflake | None
    emoji_name: str | None
    """At most one of `emoji_id` and `emoji_name` is set."""


class ThreadMember(Payload):
    """A user's membership in a thread.

    `id` and `user_id` are omitted on the thread member inside a `GUILD_CREATE` thread.

    Discord: https://docs.discord.com/developers/resources/channel#thread-member-object
    """

    id: Snowflake | UnsetType = UNSET
    user_id: Snowflake | UnsetType = UNSET
    join_timestamp: datetime
    flags: int
    member: GuildMember | UnsetType = UNSET
    """Only when asked for with `with_member`."""


class ThreadMetadata(Payload):
    """Thread-only state.

    Discord: https://docs.discord.com/developers/resources/channel#thread-metadata-object
    """

    archived: bool
    auto_archive_duration: int
    archive_timestamp: datetime
    locked: bool
    invitable: bool | UnsetType = UNSET
    create_timestamp: datetime | UnsetType | None = UNSET


class Channel(Payload):
    """A guild channel, DM, group DM or thread.

    Discord: https://docs.discord.com/developers/resources/channel#channel-object
    """

    id: Snowflake
    type: ChannelType
    guild_id: Snowflake | UnsetType = UNSET
    position: int | UnsetType = UNSET
    permission_overwrites: list[Overwrite] | UnsetType = UNSET
    name: str | UnsetType | None = UNSET
    topic: str | UnsetType | None = UNSET
    nsfw: bool | UnsetType = UNSET
    last_message_id: Snowflake | UnsetType | None = UNSET
    bitrate: int | UnsetType = UNSET
    user_limit: int | UnsetType = UNSET
    rate_limit_per_user: int | UnsetType = UNSET
    recipients: list[User] | UnsetType = UNSET
    icon: str | UnsetType | None = UNSET
    owner_id: Snowflake | UnsetType = UNSET
    application_id: Snowflake | UnsetType | None = UNSET
    managed: bool | UnsetType = UNSET
    parent_id: Snowflake | UnsetType | None = UNSET
    last_pin_timestamp: datetime | UnsetType | None = UNSET
    rtc_region: str | UnsetType | None = UNSET
    video_quality_mode: VideoQualityMode | UnsetType = UNSET
    message_count: int | UnsetType = UNSET
    member_count: int | UnsetType = UNSET
    thread_metadata: ThreadMetadata | UnsetType = UNSET
    member: ThreadMember | UnsetType = UNSET
    """The current user's membership, on threads they joined, from some endpoints only."""
    default_auto_archive_duration: int | UnsetType = UNSET
    permissions: Permissions | UnsetType = UNSET
    app_permissions: Permissions | UnsetType = UNSET
    flags: ChannelFlags | UnsetType = UNSET
    total_message_sent: int | UnsetType = UNSET
    available_tags: list[ForumTag] | UnsetType = UNSET
    applied_tags: list[Snowflake] | UnsetType = UNSET
    default_reaction_emoji: DefaultReaction | UnsetType | None = UNSET
    default_thread_rate_limit_per_user: int | UnsetType = UNSET
    default_sort_order: SortOrderType | UnsetType | None = UNSET
    default_forum_layout: ForumLayoutType | UnsetType = UNSET

    @property
    def is_obfuscated(self) -> bool:
        """Whether Discord hid this channel's metadata because the bot cannot view it.

        Discord: https://docs.discord.com/developers/resources/channel#channel-object-obfuscated-channels
        """
        return isinstance(self.flags, ChannelFlags) and self.flags.channel_obfuscated

    @property
    def visible_name(self) -> str | None:
        """The channel name, or `None` when it is unknown or obfuscated. Prefer this to `name`."""
        if self.is_obfuscated or not isinstance(self.name, str):
            return None
        return self.name


OBFUSCATED_RELIABLE_FIELDS: Final = frozenset({"id", "type", "position", "parent_id"})
"""The only `Channel` fields Discord keeps accurate on an obfuscated channel.

Discord: https://docs.discord.com/developers/resources/channel#channel-object-obfuscated-channels
"""


class FollowedChannel(Payload):
    """An announcement channel followed into another channel.

    Discord: https://docs.discord.com/developers/resources/channel#followed-channel-object
    """

    channel_id: Snowflake
    """The announcement channel."""
    webhook_id: Snowflake
    """The webhook created in the target channel."""


class ArchivedThreads(Payload):
    """A page of archived threads.

    Discord: https://docs.discord.com/developers/resources/channel#list-public-archived-threads-response-body
    """

    threads: list[Channel]
    members: list[ThreadMember]
    """The current user's membership in each returned thread they joined."""
    has_more: bool


class PartialOverwrite(Payload):
    """A permission overwrite in a request; a missing or `None` `allow` or `deny` means none.

    Discord: https://docs.discord.com/developers/resources/channel#modify-channel-json-params-guild-channel
    """

    id: Snowflake
    type: OverwriteType
    allow: Permissions | UnsetType | None = UNSET
    deny: Permissions | UnsetType | None = UNSET


class ForumTagParams(Payload):
    """A forum tag in a request. A tag without `id` is created; only `name` is required.

    Discord: https://docs.discord.com/developers/resources/channel#forum-tag-object
    """

    id: Snowflake | UnsetType = UNSET
    name: str
    """0 to 20 characters."""
    moderated: bool | UnsetType = UNSET
    emoji_id: Snowflake | UnsetType | None = UNSET
    emoji_name: str | UnsetType | None = UNSET


class EditGroupDMParams(Payload):
    """JSON body of Modify Channel for a group DM.

    Discord: https://docs.discord.com/developers/resources/channel#modify-channel-json-params-group-dm
    """

    name: str | UnsetType = UNSET
    """1 to 100 characters."""
    icon: ImageData | UnsetType = UNSET


class EditGuildChannelParams(Payload):
    """JSON body of Modify Channel for a guild channel. Needs Manage Channels.

    Each field applies to some channel types only; Discord's table lists which.

    Discord: https://docs.discord.com/developers/resources/channel#modify-channel-json-params-guild-channel
    """

    name: str | UnsetType = UNSET
    """1 to 100 characters."""
    type: ChannelType | UnsetType = UNSET
    """Only between text and announcement, in guilds with the `NEWS` feature."""
    position: int | UnsetType | None = UNSET
    topic: str | UnsetType | None = UNSET
    """Up to 1024 characters, or 4096 in forum and media channels."""
    nsfw: bool | UnsetType | None = UNSET
    rate_limit_per_user: int | UnsetType | None = UNSET
    """Slowmode in seconds, 0 to 21600."""
    bitrate: int | UnsetType | None = UNSET
    """At least 8000; the maximum depends on the channel type and the guild's Boost level."""
    user_limit: int | UnsetType | None = UNSET
    """0 for no limit; at most 99 in voice channels and 10,000 in stage channels."""
    permission_overwrites: list[PartialOverwrite] | UnsetType | None = UNSET
    """Changing overwrites needs Manage Roles."""
    parent_id: Snowflake | UnsetType | None = UNSET
    rtc_region: str | UnsetType | None = UNSET
    """A voice region ID; `None` picks one automatically."""
    video_quality_mode: VideoQualityMode | UnsetType | None = UNSET
    default_auto_archive_duration: int | UnsetType | None = UNSET
    flags: ChannelFlags | UnsetType = UNSET
    available_tags: list[ForumTagParams] | UnsetType = UNSET
    """At most 20."""
    default_reaction_emoji: DefaultReaction | UnsetType | None = UNSET
    default_thread_rate_limit_per_user: int | UnsetType = UNSET
    default_sort_order: SortOrderType | UnsetType | None = UNSET
    default_forum_layout: ForumLayoutType | UnsetType = UNSET


class EditThreadParams(Payload):
    """JSON body of Modify Channel for a thread.

    Unarchiving an unlocked thread needs only Send Messages; everything else needs Manage Threads.

    Discord: https://docs.discord.com/developers/resources/channel#modify-channel-json-params-thread
    """

    name: str | UnsetType = UNSET
    """1 to 100 characters."""
    archived: bool | UnsetType = UNSET
    auto_archive_duration: int | UnsetType = UNSET
    """Minutes: 60, 1440, 4320 or 10080."""
    locked: bool | UnsetType = UNSET
    invitable: bool | UnsetType = UNSET
    """Private threads only."""
    rate_limit_per_user: int | UnsetType | None = UNSET
    flags: ChannelFlags | UnsetType = UNSET
    """`pinned` can only be set on posts in forum and media channels."""
    applied_tags: list[Snowflake] | UnsetType = UNSET
    """At most 5."""


class EditVoiceStatusParams(Payload):
    """JSON body of Set Voice Channel Status.

    Discord: https://docs.discord.com/developers/resources/channel#set-voice-channel-status
    """

    status: str | None
    """Up to 500 characters; `None` clears it."""


class EditChannelPermissionsParams(Payload):
    """JSON body of Edit Channel Permissions. A missing or `None` `allow` or `deny` means none.

    Discord: https://docs.discord.com/developers/resources/channel#edit-channel-permissions-json-params
    """

    allow: Permissions | UnsetType | None = UNSET
    deny: Permissions | UnsetType | None = UNSET
    type: OverwriteType


class FollowChannelParams(Payload):
    """JSON body of Follow Announcement Channel.

    Discord: https://docs.discord.com/developers/resources/channel#follow-announcement-channel-json-params
    """

    webhook_channel_id: Snowflake
    """The channel the announcements are posted to."""


class AddRecipientParams(Payload):
    """JSON body of Group DM Add Recipient.

    Discord: https://docs.discord.com/developers/resources/channel#group-dm-add-recipient-json-params
    """

    REDACTED_FIELDS = frozenset({"access_token"})

    access_token: str
    """An OAuth2 token of the user, with the `gdm.join` scope."""
    nick: str


class CreateThreadFromMessageParams(Payload):
    """JSON body of Start Thread from Message.

    Discord: https://docs.discord.com/developers/resources/channel#start-thread-from-message-json-params
    """

    name: str
    """1 to 100 characters."""
    auto_archive_duration: int | UnsetType = UNSET
    """Minutes: 60, 1440, 4320 or 10080."""
    rate_limit_per_user: int | UnsetType | None = UNSET


class CreateThreadParams(Payload):
    """JSON body of Start Thread without Message.

    Discord: https://docs.discord.com/developers/resources/channel#start-thread-without-message-json-params
    """

    name: str
    """1 to 100 characters."""
    auto_archive_duration: int | UnsetType = UNSET
    """Minutes: 60, 1440, 4320 or 10080."""
    type: ChannelType | UnsetType = UNSET
    """Discord's default is `PRIVATE_THREAD`; a future API version will require it."""
    invitable: bool | UnsetType = UNSET
    """Private threads only."""
    rate_limit_per_user: int | UnsetType | None = UNSET


class ListThreadMembersParams(Payload):
    """Query of List Thread Members. With `with_member`, the results are paginated.

    Discord: https://docs.discord.com/developers/resources/channel#list-thread-members-query-string-params
    """

    with_member: bool | UnsetType = UNSET
    after: Snowflake | UnsetType = UNSET
    """A user ID."""
    limit: int | UnsetType = UNSET
    """1 to 100; Discord's default is 100."""


class ListArchivedThreadsParams(Payload):
    """Query of List Public Archived Threads and List Private Archived Threads.

    Discord: https://docs.discord.com/developers/resources/channel#list-public-archived-threads-query-string-params
    """

    before: datetime | UnsetType = UNSET
    """Threads archived before this time."""
    limit: int | UnsetType = UNSET


class ListJoinedPrivateArchivedThreadsParams(Payload):
    """Query of List Joined Private Archived Threads, which pages by thread ID.

    Discord: https://docs.discord.com/developers/resources/channel#list-joined-private-archived-threads-query-string-params
    """

    before: Snowflake | UnsetType = UNSET
    """Threads with a lower ID."""
    limit: int | UnsetType = UNSET


class CreateChannelParams(Payload):
    """JSON body of Create Guild Channel. Needs Manage Channels.

    Each field applies to some channel types only; Discord's table lists which.

    Discord: https://docs.discord.com/developers/resources/guild#create-guild-channel-json-params
    """

    name: str
    """1 to 100 characters."""
    type: ChannelType | UnsetType | None = UNSET
    topic: str | UnsetType | None = UNSET
    bitrate: int | UnsetType | None = UNSET
    user_limit: int | UnsetType | None = UNSET
    rate_limit_per_user: int | UnsetType | None = UNSET
    position: int | UnsetType | None = UNSET
    permission_overwrites: list[PartialOverwrite] | UnsetType | None = UNSET
    """Only permissions the bot has can be set; Manage Roles only by administrators."""
    parent_id: Snowflake | UnsetType | None = UNSET
    nsfw: bool | UnsetType | None = UNSET
    rtc_region: str | UnsetType | None = UNSET
    video_quality_mode: VideoQualityMode | UnsetType | None = UNSET
    default_auto_archive_duration: int | UnsetType | None = UNSET
    default_reaction_emoji: DefaultReaction | UnsetType | None = UNSET
    available_tags: list[ForumTagParams] | UnsetType | None = UNSET
    default_sort_order: SortOrderType | UnsetType | None = UNSET
    default_forum_layout: ForumLayoutType | UnsetType | None = UNSET
    default_thread_rate_limit_per_user: int | UnsetType | None = UNSET
    flags: ChannelFlags | UnsetType | None = UNSET


class ChannelPositionParams(Payload):
    """One channel's change, in the body of Modify Guild Channel Positions.

    At most one entry per request may change `parent_id`.

    Discord: https://docs.discord.com/developers/resources/guild#modify-guild-channel-positions-json-params
    """

    id: Snowflake
    position: int | UnsetType | None = UNSET
    lock_permissions: bool | UnsetType | None = UNSET
    """Sync the overwrites with the new parent; needs Manage Roles."""
    parent_id: Snowflake | UnsetType | None = UNSET


class ActiveThreads(Payload):
    """A guild's active threads, newest first.

    Discord: https://docs.discord.com/developers/resources/guild#list-active-guild-threads-response-body
    """

    threads: list[Channel]
    members: list[ThreadMember]
    """The current user's membership in each returned thread they joined."""
