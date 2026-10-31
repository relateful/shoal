"""Permissions and roles.

Discord: https://docs.discord.com/developers/topics/permissions
"""

from msgspec import UNSET, UnsetType

from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload


class Permissions(BaseFlags):
    """A permission bit set. Discord sends it as a decimal string.

    Discord: https://docs.discord.com/developers/topics/permissions#permissions-bitwise-permission-flags
    """

    __slots__ = ()

    WIRE_AS_STRING = True

    create_instant_invite = flag(0)
    kick_members = flag(1)
    ban_members = flag(2)
    administrator = flag(3)
    manage_channels = flag(4)
    manage_guild = flag(5)
    add_reactions = flag(6)
    view_audit_log = flag(7)
    priority_speaker = flag(8)
    stream = flag(9)
    view_channel = flag(10)
    send_messages = flag(11)
    send_tts_messages = flag(12)
    manage_messages = flag(13)
    embed_links = flag(14)
    attach_files = flag(15)
    read_message_history = flag(16)
    mention_everyone = flag(17)
    use_external_emojis = flag(18)
    view_guild_insights = flag(19)
    connect = flag(20)
    speak = flag(21)
    mute_members = flag(22)
    deafen_members = flag(23)
    move_members = flag(24)
    use_vad = flag(25)
    change_nickname = flag(26)
    manage_nicknames = flag(27)
    manage_roles = flag(28)
    manage_webhooks = flag(29)
    manage_guild_expressions = flag(30)
    use_application_commands = flag(31)
    request_to_speak = flag(32)
    manage_events = flag(33)
    manage_threads = flag(34)
    create_public_threads = flag(35)
    create_private_threads = flag(36)
    use_external_stickers = flag(37)
    send_messages_in_threads = flag(38)
    use_embedded_activities = flag(39)
    moderate_members = flag(40)
    view_creator_monetization_analytics = flag(41)
    use_soundboard = flag(42)
    create_guild_expressions = flag(43)
    create_events = flag(44)
    use_external_sounds = flag(45)
    send_voice_messages = flag(46)
    set_voice_channel_status = flag(48)
    send_polls = flag(49)
    use_external_apps = flag(50)
    pin_messages = flag(51)
    bypass_slowmode = flag(52)


class RoleFlags(BaseFlags):
    """Flags on a role.

    Discord: https://docs.discord.com/developers/topics/permissions#role-object-role-flags
    """

    __slots__ = ()

    in_prompt = flag(0)


class RoleTags(Payload):
    """Why a role exists (bot, booster, integration, subscription).

    Several tags are documented with type `null`: the key being present means `True`. Use the
    `is_*` properties rather than reading those fields directly.

    Discord: https://docs.discord.com/developers/topics/permissions#role-object-role-tags-structure
    """

    bot_id: Snowflake | UnsetType = UNSET
    integration_id: Snowflake | UnsetType = UNSET
    premium_subscriber: UnsetType | None = UNSET
    subscription_listing_id: Snowflake | UnsetType = UNSET
    available_for_purchase: UnsetType | None = UNSET
    guild_connections: UnsetType | None = UNSET

    @property
    def is_premium_subscriber(self) -> bool:
        """Whether this is the guild's Booster role."""
        return self.premium_subscriber is None

    @property
    def is_available_for_purchase(self) -> bool:
        """Whether this role subscription can be purchased."""
        return self.available_for_purchase is None

    @property
    def is_guild_connection(self) -> bool:
        """Whether this is a linked role."""
        return self.guild_connections is None


class RoleColors(Payload):
    """A role's solid, gradient or holographic colours.

    Discord: https://docs.discord.com/developers/topics/permissions#role-object-role-colors-object
    """

    primary_color: int
    secondary_color: int | None
    tertiary_color: int | None


class PermissionsResponse(Payload):
    """The permissions Discord computed for a member or role, in a guild or a channel.

    Discord: https://docs.discord.com/developers/resources/guild#get-guild-member-permissions-permissions-response
    """

    permissions: Permissions


class Role(Payload):
    """A guild role.

    Discord: https://docs.discord.com/developers/topics/permissions#role-object
    """

    id: Snowflake
    name: str
    color: int
    colors: RoleColors
    hoist: bool
    icon: str | UnsetType | None = UNSET
    unicode_emoji: str | UnsetType | None = UNSET
    position: int
    permissions: Permissions
    managed: bool
    mentionable: bool
    tags: RoleTags | UnsetType = UNSET
    flags: RoleFlags
