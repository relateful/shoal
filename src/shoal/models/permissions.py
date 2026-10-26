"""Computing a member's permissions in a guild and in a channel, the way Discord does.

These are pure functions over payload data, so a dashboard can use them without a client. The models
(`Member.guild_permissions`, `GuildChannel.permissions_for`) call them with what the cache holds.

Discord: https://docs.discord.com/developers/topics/permissions#permission-overwrites
"""

from collections.abc import Iterable, Mapping

from shoal.core.snowflake import Snowflake
from shoal.payloads.channel import ChannelType, Overwrite, OverwriteType
from shoal.payloads.permissions import Permissions

_SENDING = Permissions(send_tts_messages=True, mention_everyone=True, embed_links=True, attach_files=True)
"""Implicitly denied without Send Messages.

Discord: https://docs.discord.com/developers/topics/permissions#implicit-permissions
"""
_VOICE_ONLY = Permissions(
    connect=True,
    speak=True,
    mute_members=True,
    deafen_members=True,
    move_members=True,
    use_vad=True,
    priority_speaker=True,
    stream=True,
    request_to_speak=True,
    use_embedded_activities=True,
    use_soundboard=True,
    use_external_sounds=True,
    set_voice_channel_status=True,
    manage_channels=True,
    manage_roles=True,
)
"""Implicitly denied in a voice or stage channel without Connect (Discord names Manage Channels as an
example; the voice permissions and Manage Roles go with it).

Discord: https://docs.discord.com/developers/topics/permissions#implicit-permissions
"""
_WHILE_TIMED_OUT = Permissions(view_channel=True, read_message_history=True)
"""All a timed out member keeps, unless they own the guild or are an administrator.

Discord: https://docs.discord.com/developers/topics/permissions#permissions-for-timed-out-members
"""
_VOICE_KINDS = frozenset({ChannelType.GUILD_VOICE, ChannelType.GUILD_STAGE_VOICE})


def guild_permissions(
    *,
    guild_id: int,
    owner_id: int,
    user_id: int,
    role_permissions: Mapping[int, Permissions],
    member_roles: Iterable[int],
    timed_out: bool = False,
) -> Permissions:
    """A member's guild-wide permissions: @everyone's, plus each of their roles'.

    Args:
        guild_id: The guild, whose ID is also the @everyone role's.
        owner_id: The guild owner, who has every permission.
        user_id: The member.
        role_permissions: The permissions of the guild's roles, by role ID. Roles missing from it
            (deleted, or not cached) add nothing.
        member_roles: The member's role IDs, without @everyone.
        timed_out: Whether the member is timed out; they then keep only View Channel and Read
            Message History, unless they own the guild or are an administrator.

    Discord: https://docs.discord.com/developers/topics/permissions#permission-overwrites
    """
    if user_id == owner_id:
        return Permissions.all()
    permissions = role_permissions.get(guild_id, Permissions.none())
    for role_id in member_roles:
        permissions |= role_permissions.get(role_id, Permissions.none())
    if permissions.administrator:
        return Permissions.all()
    if timed_out:
        return permissions & _WHILE_TIMED_OUT
    return permissions


def channel_permissions(
    base: Permissions,
    *,
    guild_id: int,
    user_id: int,
    member_roles: Iterable[int],
    overwrites: Iterable[Overwrite],
    channel_type: ChannelType | None = None,
    timed_out: bool = False,
) -> Permissions:
    """A member's permissions in a channel: `base` (from `guild_permissions`) with the overwrites.

    Applies @everyone's overwrite, then the member's roles' overwrites together, then the member's
    own, and then the implicit rules: without View Channel nothing else applies, without Send
    Messages the sending extras do not either, and in a voice or stage channel without Connect the
    voice permissions do not. For a thread, pass the parent's overwrites and use
    `thread_permissions` on the result.

    Discord: https://docs.discord.com/developers/topics/permissions#permission-overwrites
    """
    if base.administrator:
        return Permissions.all()
    by_target = {overwrite.id: overwrite for overwrite in overwrites}
    permissions = base
    everyone = by_target.get(Snowflake(guild_id))
    if everyone is not None:
        permissions = permissions.without(everyone.deny) | everyone.allow
    allow, deny = Permissions.none(), Permissions.none()
    for role_id in member_roles:
        overwrite = by_target.get(Snowflake(role_id))
        if overwrite is not None and overwrite.type is OverwriteType.ROLE:
            allow |= overwrite.allow
            deny |= overwrite.deny
    permissions = permissions.without(deny) | allow
    own = by_target.get(Snowflake(user_id))
    if own is not None and own.type is OverwriteType.MEMBER:
        permissions = permissions.without(own.deny) | own.allow
    if timed_out:
        permissions &= _WHILE_TIMED_OUT
    if not permissions.view_channel:
        return Permissions.none()
    if not permissions.send_messages:
        permissions = permissions.without(_SENDING)
    if channel_type in _VOICE_KINDS and not permissions.connect:
        permissions = permissions.without(_VOICE_ONLY)
    return permissions


def thread_permissions(parent: Permissions) -> Permissions:
    """A member's permissions in a thread, from their permissions in its parent channel.

    Threads inherit everything but Send Messages: sending in a thread needs Send Messages in
    Threads, so `send_messages` here reflects that permission.

    Discord: https://docs.discord.com/developers/topics/permissions#inherited-permissions-threads
    """
    if parent.administrator:
        return parent
    permissions = parent.with_flags(send_messages=parent.send_messages_in_threads)
    if not permissions.send_messages:
        permissions = permissions.without(_SENDING)
    return permissions
