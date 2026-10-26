import pytest

from shoal.core.snowflake import Snowflake
from shoal.models.permissions import channel_permissions, guild_permissions, thread_permissions
from shoal.payloads import ChannelType, Overwrite, OverwriteType, Permissions

GUILD = 10
OWNER = 1
USER = 2
MODS = 20
MUTED = 21

EVERYONE_PERMISSIONS = Permissions(view_channel=True, send_messages=True, read_message_history=True)


def overwrite(
    target: int, kind: OverwriteType, *, allow: Permissions | None = None, deny: Permissions | None = None
) -> Overwrite:
    return Overwrite(
        id=Snowflake(target), type=kind, allow=allow or Permissions.none(), deny=deny or Permissions.none()
    )


def base(*roles: int, timed_out: bool = False, user_id: int = USER) -> Permissions:
    return guild_permissions(
        guild_id=GUILD,
        owner_id=OWNER,
        user_id=user_id,
        role_permissions={
            GUILD: EVERYONE_PERMISSIONS,
            MODS: Permissions(kick_members=True, manage_messages=True),
            MUTED: Permissions.none(),
        },
        member_roles=roles,
        timed_out=timed_out,
    )


def test_guild_permissions_add_everyone_and_each_role() -> None:
    assert base() == EVERYONE_PERMISSIONS
    assert base(MODS) == EVERYONE_PERMISSIONS | Permissions(kick_members=True, manage_messages=True)


def test_the_owner_and_administrators_have_everything() -> None:
    assert base(user_id=OWNER) == Permissions.all()
    admin = guild_permissions(
        guild_id=GUILD,
        owner_id=OWNER,
        user_id=USER,
        role_permissions={GUILD: Permissions.none(), MODS: Permissions(administrator=True)},
        member_roles=[MODS],
    )
    assert admin == Permissions.all()


def test_unknown_roles_add_nothing() -> None:
    assert base(999) == EVERYONE_PERMISSIONS


def test_timed_out_members_keep_only_viewing_and_history() -> None:
    assert base(MODS, timed_out=True) == Permissions(view_channel=True, read_message_history=True)
    assert base(user_id=OWNER, timed_out=True) == Permissions.all()


def in_channel(
    *overwrites: Overwrite, roles: tuple[int, ...] = (), kind: ChannelType | None = None
) -> Permissions:
    return channel_permissions(
        base(*roles),
        guild_id=GUILD,
        user_id=USER,
        member_roles=roles,
        overwrites=overwrites,
        channel_type=kind,
    )


def test_overwrites_apply_everyone_then_roles_then_the_member() -> None:
    no_send = overwrite(GUILD, OverwriteType.ROLE, deny=Permissions(send_messages=True))
    mods_send = overwrite(MODS, OverwriteType.ROLE, allow=Permissions(send_messages=True))
    muted = overwrite(MUTED, OverwriteType.ROLE, deny=Permissions(send_messages=True))
    assert not in_channel(no_send).send_messages
    assert in_channel(no_send, mods_send, roles=(MODS,)).send_messages
    # Role overwrites are combined first: an allow from any role beats a deny from another.
    assert in_channel(no_send, mods_send, muted, roles=(MODS, MUTED)).send_messages
    member_deny = overwrite(USER, OverwriteType.MEMBER, deny=Permissions(send_messages=True))
    assert not in_channel(mods_send, member_deny, roles=(MODS,)).send_messages


def test_an_overwrite_for_a_role_the_member_lacks_does_nothing() -> None:
    mods_only = overwrite(MODS, OverwriteType.ROLE, deny=Permissions(view_channel=True))
    assert in_channel(mods_only).view_channel


def test_an_overwrite_only_counts_for_its_kind() -> None:
    # A member overwrite whose ID happens to match a role the member has is not a role overwrite.
    impostor = overwrite(MODS, OverwriteType.MEMBER, deny=Permissions(view_channel=True))
    assert in_channel(impostor, roles=(MODS,)).view_channel


def test_without_view_channel_nothing_applies() -> None:
    hidden = overwrite(GUILD, OverwriteType.ROLE, deny=Permissions(view_channel=True))
    assert in_channel(hidden) == Permissions.none()


def test_without_send_messages_the_sending_extras_are_denied() -> None:
    no_send = overwrite(
        GUILD,
        OverwriteType.ROLE,
        allow=Permissions(attach_files=True, embed_links=True),
        deny=Permissions(send_messages=True),
    )
    permissions = in_channel(no_send)
    assert not permissions.attach_files
    assert not permissions.embed_links


@pytest.mark.parametrize("kind", [ChannelType.GUILD_VOICE, ChannelType.GUILD_STAGE_VOICE])
def test_without_connect_voice_permissions_are_denied(kind: ChannelType) -> None:
    speak = overwrite(GUILD, OverwriteType.ROLE, allow=Permissions(speak=True, manage_channels=True))
    assert not in_channel(speak, kind=kind).speak
    assert not in_channel(speak, kind=kind).manage_channels
    connect = overwrite(USER, OverwriteType.MEMBER, allow=Permissions(connect=True))
    assert in_channel(speak, connect, kind=kind).speak
    assert in_channel(speak, kind=ChannelType.GUILD_TEXT).speak


def test_administrators_ignore_overwrites() -> None:
    hidden = overwrite(GUILD, OverwriteType.ROLE, deny=Permissions(view_channel=True))
    administrator = Permissions(administrator=True)
    assert (
        channel_permissions(administrator, guild_id=GUILD, user_id=USER, member_roles=(), overwrites=[hidden])
        == Permissions.all()
    )


def test_permissions_discord_adds_later_survive_overwrites() -> None:
    newer = Permissions(int(EVERYONE_PERMISSIONS) | (1 << 60))
    deny = overwrite(GUILD, OverwriteType.ROLE, deny=Permissions(send_messages=True))
    result = channel_permissions(newer, guild_id=GUILD, user_id=USER, member_roles=(), overwrites=[deny])
    assert result.unknown_bits == 1 << 60


def test_timed_out_members_are_limited_in_channels_too() -> None:
    allow_all = overwrite(
        USER, OverwriteType.MEMBER, allow=Permissions(send_messages=True, attach_files=True)
    )
    result = channel_permissions(
        EVERYONE_PERMISSIONS,
        guild_id=GUILD,
        user_id=USER,
        member_roles=(),
        overwrites=[allow_all],
        timed_out=True,
    )
    assert result == Permissions(view_channel=True, read_message_history=True)


def test_threads_need_send_messages_in_threads() -> None:
    parent = Permissions(view_channel=True, send_messages=True, attach_files=True)
    assert not thread_permissions(parent).send_messages
    assert not thread_permissions(parent).attach_files
    allowed = thread_permissions(parent | Permissions(send_messages_in_threads=True))
    assert allowed.send_messages
    assert allowed.attach_files
    assert thread_permissions(Permissions.all()) == Permissions.all()
