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

Not yet modeled: `Channel.member` (thread member), forum tags, default reaction emoji, sort order and
forum layout enums. Decoding ignores those keys until they are added.
"""

from datetime import datetime
from typing import Final

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum
from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload
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
    default_auto_archive_duration: int | UnsetType = UNSET
    permissions: Permissions | UnsetType = UNSET
    app_permissions: Permissions | UnsetType = UNSET
    flags: ChannelFlags | UnsetType = UNSET
    total_message_sent: int | UnsetType = UNSET
    applied_tags: list[Snowflake] | UnsetType = UNSET
    default_thread_rate_limit_per_user: int | UnsetType = UNSET

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


class ThreadMember(Payload):
    """A user's membership in a thread.

    `id` and `user_id` are omitted on the thread member inside a `GUILD_CREATE` thread; `member` is
    only present when explicitly requested.

    Discord: https://docs.discord.com/developers/resources/channel#thread-member-object
    """

    id: Snowflake | UnsetType = UNSET
    user_id: Snowflake | UnsetType = UNSET
    join_timestamp: datetime
    flags: int
