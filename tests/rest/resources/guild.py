import base64
from datetime import UTC, datetime

from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    AddMemberParams,
    BanParams,
    BulkBanParams,
    ChannelPositionParams,
    ChannelType,
    CreateChannelParams,
    CreateRoleParams,
    EditCurrentMemberParams,
    EditGuildParams,
    EditIncidentActionsParams,
    EditMemberParams,
    EditOnboardingParams,
    EditRoleParams,
    EditWelcomeScreenParams,
    EditWidgetSettingsParams,
    GetPruneCountParams,
    ListBansParams,
    ListMembersParams,
    OnboardingMode,
    OnboardingPromptParams,
    PromptOptionParams,
    PromptType,
    PruneParams,
    RoleColors,
    RolePositionParams,
    SearchMembersParams,
    VerificationLevel,
    WelcomeScreenChannel,
    WidgetStyle,
)
from tests.support.json_payloads import (
    CHANNEL,
    GUILD,
    INTEGRATION,
    INVITE_WITH_METADATA,
    MEMBER,
    REGION,
    ROLE,
    THREAD,
    THREAD_MEMBER,
    USER,
)
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

G = "/guilds/2"
PREVIEW: dict[str, object] = {
    "id": "197038439483310086",
    "name": "Discord Testers",
    "icon": "f64c482b807da4f539cff778d174971c",
    "splash": None,
    "discovery_splash": None,
    "emojis": [],
    "features": ["DISCOVERABLE", "VANITY_URL", "COMMUNITY"],
    "approximate_member_count": 60814,
    "approximate_presence_count": 20034,
    "description": "The official place to report Discord Bugs!",
    "stickers": [],
}
"""Discord's example, with fewer features."""
BAN: dict[str, object] = {"reason": "mentioning b1nzy", "user": USER}
BOT_INTEGRATION: dict[str, object] = {
    "id": "34",
    "name": "Shoal",
    "type": "discord",
    "enabled": True,
    "account": {"id": "1", "name": "Shoal"},
    "application": {"id": "7", "name": "Shoal", "icon": None, "description": "", "bot": USER},
    "scopes": ["bot", "applications.commands"],
}
WIDGET: dict[str, object] = {
    "id": "290926798626999250",
    "name": "Test Server",
    "instant_invite": "https://discord.com/invite/abcdefg",
    "channels": [{"id": "705216630279993882", "name": "elephant", "position": 2}],
    "members": [
        {
            "id": "0",
            "username": "1234",
            "discriminator": "0000",
            "avatar": None,
            "status": "online",
            "avatar_url": "https://cdn.discordapp.com/widget-avatars/abc",
        }
    ],
    "presence_count": 1,
}
"""Discord's example, with a shorter avatar URL."""
WELCOME: dict[str, object] = {
    "description": "Discord Developers is a place to learn about Discord's API.",
    "welcome_channels": [
        {
            "channel_id": "697138785317814292",
            "description": "Follow for official Discord API updates",
            "emoji_id": None,
            "emoji_name": "\N{SATELLITE ANTENNA}",
        }
    ],
}
ONBOARDING: dict[str, object] = {
    "guild_id": "960007075288915998",
    "prompts": [
        {
            "id": "1067461047608422473",
            "type": 0,
            "options": [
                {
                    "id": "1067461047608422476",
                    "channel_ids": ["962007075288916001"],
                    "role_ids": [],
                    "emoji": {"id": "1070002302032826408", "name": "chat", "animated": False},
                    "title": "Chat with Friends",
                    "description": "",
                }
            ],
            "title": "What do you want to do in this community?",
            "single_select": False,
            "required": False,
            "in_onboarding": True,
        }
    ],
    "default_channel_ids": ["998678771706110023"],
    "enabled": True,
    "mode": 0,
}
"""Discord's example, trimmed, in the field tables' order and with the `mode` it leaves out."""
INCIDENTS: dict[str, object] = {
    "invites_disabled_until": "2026-01-01T12:00:00+00:00",
    "dms_disabled_until": None,
}
PNG = b"\x89PNG\r\n\x1a\n"
TIMED_OUT_MEMBER: dict[str, object] = {
    "user": USER,
    "nick": None,
    "avatar": None,
    "roles": ["5"],
    "joined_at": "2024-01-01T00:00:00+00:00",
    "premium_since": None,
    "deaf": False,
    "mute": False,
    "flags": 4,
    "pending": False,
    "communication_disabled_until": "2026-01-01T00:00:00+00:00",
}
"""A member with the timeout set and the nullable fields sent as `null`."""

CASES = [
    EndpointCase(
        name="get guild",
        call=lambda client: client.guilds.get(2),
        method="GET",
        path=f"{G}?with_counts=false",
        response={**GUILD, "incidents_data": INCIDENTS},
    ),
    EndpointCase(
        name="get guild with counts",
        call=lambda client: client.guilds.get(2, with_counts=True),
        method="GET",
        path=f"{G}?with_counts=true",
        response={**GUILD, "approximate_member_count": 120, "approximate_presence_count": 40},
    ),
    EndpointCase(
        name="member permissions",
        call=lambda client: client.guilds.get_member_permissions(2, 5),
        method="GET",
        path=f"{G}/permissions/member/5",
        response={"permissions": "1024"},
        result="1024",
    ),
    EndpointCase(
        name="role permissions",
        call=lambda client: client.guilds.get_role_permissions(2, 6),
        method="GET",
        path=f"{G}/permissions/role/6",
        response={"permissions": "2048"},
        result="2048",
    ),
    EndpointCase(
        name="preview",
        call=lambda client: client.guilds.get_preview(2),
        method="GET",
        path=f"{G}/preview",
        response=PREVIEW,
    ),
    EndpointCase(
        name="modify guild",
        call=lambda client: client.guilds.edit(
            2,
            EditGuildParams(name="g", verification_level=VerificationLevel.HIGH, icon=None),
            reason="rebrand",
        ),
        method="PATCH",
        path=G,
        body={"name": "g", "verification_level": 3, "icon": None},
        response=GUILD,
        reason="rebrand",
    ),
    EndpointCase(
        name="channels",
        call=lambda client: client.channels.list(2),
        method="GET",
        path=f"{G}/channels",
        response=[CHANNEL],
    ),
    EndpointCase(
        name="create channel",
        call=lambda client: client.channels.create(
            2, CreateChannelParams(name="general", type=ChannelType.GUILD_TEXT, topic=None)
        ),
        method="POST",
        path=f"{G}/channels",
        body={"name": "general", "type": 0, "topic": None},
        response=CHANNEL,
    ),
    EndpointCase(
        name="channel positions",
        call=lambda client: client.channels.edit_positions(
            2,
            [
                ChannelPositionParams(id=Snowflake(3), position=0),
                ChannelPositionParams(id=Snowflake(4), parent_id=None, lock_permissions=True),
            ],
            reason="tidy",
        ),
        method="PATCH",
        path=f"{G}/channels",
        body=[{"id": "3", "position": 0}, {"id": "4", "lock_permissions": True, "parent_id": None}],
        reason="tidy",
    ),
    EndpointCase(
        name="active threads",
        call=lambda client: client.threads.list_active(2),
        method="GET",
        path=f"{G}/threads/active",
        response={"threads": [THREAD], "members": [THREAD_MEMBER]},
    ),
    EndpointCase(
        name="get member",
        call=lambda client: client.members.get(2, 1),
        method="GET",
        path=f"{G}/members/1",
        response=MEMBER,
    ),
    EndpointCase(
        name="list members",
        call=lambda client: client.members.list(2, ListMembersParams(limit=1000, after=Snowflake(1))),
        method="GET",
        path=f"{G}/members?limit=1000&after=1",
        response=[MEMBER],
    ),
    EndpointCase(
        name="search members",
        call=lambda client: client.members.search(2, SearchMembersParams(query="ad", limit=5)),
        method="GET",
        path=f"{G}/members/search?query=ad&limit=5",
        response=[MEMBER],
    ),
    EndpointCase(
        name="add member",
        call=lambda client: client.members.add(
            2, 1, AddMemberParams(access_token="oauth", roles=[Snowflake(5)])
        ),
        method="PUT",
        path=f"{G}/members/1",
        body={"access_token": "oauth", "roles": ["5"]},
        response=MEMBER,
    ),
    EndpointCase(
        name="add a member who is already in",
        call=lambda client: client.members.add(2, 1, AddMemberParams(access_token="oauth")),
        method="PUT",
        path=f"{G}/members/1",
        body={"access_token": "oauth"},
    ),
    EndpointCase(
        name="time out a member",
        call=lambda client: client.members.edit(
            2,
            1,
            EditMemberParams(communication_disabled_until=datetime(2026, 1, 1, tzinfo=UTC), channel_id=None),
            reason="spam",
        ),
        method="PATCH",
        path=f"{G}/members/1",
        body={"channel_id": None, "communication_disabled_until": "2026-01-01T00:00:00Z"},
        response=TIMED_OUT_MEMBER,
        reason="spam",
    ),
    EndpointCase(
        name="modify current member",
        call=lambda client: client.members.edit_me(2, EditCurrentMemberParams(nick="Shoal", bio=None)),
        method="PATCH",
        path=f"{G}/members/@me",
        body={"nick": "Shoal", "bio": None},
        response=MEMBER,
    ),
    EndpointCase(
        name="modify current nick",
        call=lambda client: client.members.edit_my_nick(2, None),
        method="PATCH",
        path=f"{G}/members/@me/nick",
        body={"nick": None},
    ),
    EndpointCase(
        name="add member role",
        call=lambda client: client.members.add_role(2, 1, 5, reason="promoted"),
        method="PUT",
        path=f"{G}/members/1/roles/5",
        reason="promoted",
    ),
    EndpointCase(
        name="remove member role",
        call=lambda client: client.members.remove_role(2, 1, 5),
        method="DELETE",
        path=f"{G}/members/1/roles/5",
    ),
    EndpointCase(
        name="kick",
        call=lambda client: client.members.kick(2, 1, reason="rules"),
        method="DELETE",
        path=f"{G}/members/1",
        reason="rules",
    ),
    EndpointCase(
        name="bans",
        call=lambda client: client.members.list_bans(2, ListBansParams(limit=10, after=Snowflake(1))),
        method="GET",
        path=f"{G}/bans?limit=10&after=1",
        response=[BAN],
    ),
    EndpointCase(
        name="ban",
        call=lambda client: client.members.get_ban(2, 1),
        method="GET",
        path=f"{G}/bans/1",
        response=BAN,
    ),
    EndpointCase(
        name="create ban",
        call=lambda client: client.members.ban(2, 1, BanParams(delete_message_seconds=3600), reason="raid"),
        method="PUT",
        path=f"{G}/bans/1",
        body={"delete_message_seconds": 3600},
        reason="raid",
    ),
    EndpointCase(
        name="create ban without deleting messages",
        call=lambda client: client.members.ban(2, 1),
        method="PUT",
        path=f"{G}/bans/1",
    ),
    EndpointCase(
        name="unban",
        call=lambda client: client.members.unban(2, 1, reason="appeal"),
        method="DELETE",
        path=f"{G}/bans/1",
        reason="appeal",
    ),
    EndpointCase(
        name="bulk ban",
        call=lambda client: client.members.bulk_ban(2, BulkBanParams(user_ids=[Snowflake(1), Snowflake(8)])),
        method="POST",
        path=f"{G}/bulk-ban",
        body={"user_ids": ["1", "8"]},
        response={"banned_users": ["1"], "failed_users": ["8"]},
    ),
    EndpointCase(
        name="roles",
        call=lambda client: client.roles.list(2),
        method="GET",
        path=f"{G}/roles",
        response=[ROLE],
    ),
    EndpointCase(
        name="role",
        call=lambda client: client.roles.get(2, 5),
        method="GET",
        path=f"{G}/roles/5",
        response=ROLE,
    ),
    EndpointCase(
        name="role member counts",
        call=lambda client: client.roles.get_member_counts(2),
        method="GET",
        path=f"{G}/roles/member-counts",
        response={"613425648685547541": 1337, "697138785317814292": 67},
    ),
    EndpointCase(
        name="create role",
        call=lambda client: client.roles.create(
            2,
            CreateRoleParams(
                name="mods", colors=RoleColors(primary_color=255, secondary_color=None, tertiary_color=None)
            ),
        ),
        method="POST",
        path=f"{G}/roles",
        body={
            "name": "mods",
            "colors": {"primary_color": 255, "secondary_color": None, "tertiary_color": None},
        },
        response=ROLE,
    ),
    EndpointCase(
        name="create role with defaults",
        call=lambda client: client.roles.create(2),
        method="POST",
        path=f"{G}/roles",
        body={},
        response=ROLE,
    ),
    EndpointCase(
        name="role positions",
        call=lambda client: client.roles.edit_positions(2, [RolePositionParams(id=Snowflake(5), position=2)]),
        method="PATCH",
        path=f"{G}/roles",
        body=[{"id": "5", "position": 2}],
        response=[ROLE],
    ),
    EndpointCase(
        name="modify role",
        call=lambda client: client.roles.edit(2, 5, EditRoleParams(icon=None, mentionable=False)),
        method="PATCH",
        path=f"{G}/roles/5",
        body={"icon": None, "mentionable": False},
        response=ROLE,
    ),
    EndpointCase(
        name="delete role",
        call=lambda client: client.roles.delete(2, 5, reason="unused"),
        method="DELETE",
        path=f"{G}/roles/5",
        reason="unused",
    ),
    EndpointCase(
        name="prune count",
        call=lambda client: client.guilds.get_prune_count(
            2, GetPruneCountParams(days=30, include_roles=[Snowflake(5), Snowflake(6)])
        ),
        method="GET",
        path=f"{G}/prune?days=30&include_roles=5%2C6",
        response={"pruned": 12},
    ),
    EndpointCase(
        name="prune count with defaults",
        call=lambda client: client.guilds.get_prune_count(2),
        method="GET",
        path=f"{G}/prune",
        response={"pruned": 3},
    ),
    EndpointCase(
        name="prune count with no extra roles",
        call=lambda client: client.guilds.get_prune_count(2, GetPruneCountParams(include_roles=[])),
        method="GET",
        path=f"{G}/prune",
        response={"pruned": 3},
    ),
    EndpointCase(
        name="prune",
        call=lambda client: client.guilds.prune(
            2, PruneParams(days=30, compute_prune_count=False), reason="cleanup"
        ),
        method="POST",
        path=f"{G}/prune",
        body={"days": 30, "compute_prune_count": False},
        response={"pruned": None},
        reason="cleanup",
    ),
    EndpointCase(
        name="voice regions",
        call=lambda client: client.guilds.list_voice_regions(2),
        method="GET",
        path=f"{G}/regions",
        response=[REGION],
    ),
    EndpointCase(
        name="invites",
        call=lambda client: client.invites.list(2),
        method="GET",
        path=f"{G}/invites",
        response=[INVITE_WITH_METADATA],
    ),
    EndpointCase(
        name="integrations",
        call=lambda client: client.guilds.list_integrations(2),
        method="GET",
        path=f"{G}/integrations",
        response=[INTEGRATION, BOT_INTEGRATION],
    ),
    EndpointCase(
        name="delete integration",
        call=lambda client: client.guilds.delete_integration(2, 33, reason="unused"),
        method="DELETE",
        path=f"{G}/integrations/33",
        reason="unused",
    ),
    EndpointCase(
        name="widget settings",
        call=lambda client: client.guilds.get_widget_settings(2),
        method="GET",
        path=f"{G}/widget",
        response={"enabled": True, "channel_id": "41771983444115456"},
    ),
    EndpointCase(
        name="modify widget",
        call=lambda client: client.guilds.edit_widget_settings(
            2, EditWidgetSettingsParams(enabled=False, channel_id=None)
        ),
        method="PATCH",
        path=f"{G}/widget",
        body={"enabled": False, "channel_id": None},
        response={"enabled": False, "channel_id": None},
    ),
    EndpointCase(
        name="widget",
        call=lambda client: client.guilds.get_widget(2),
        method="GET",
        path=f"{G}/widget.json",
        response=WIDGET,
    ),
    EndpointCase(
        name="vanity url",
        call=lambda client: client.guilds.get_vanity_url(2),
        method="GET",
        path=f"{G}/vanity-url",
        response={"code": "abc", "uses": 12},
    ),
    EndpointCase(
        name="widget image",
        call=lambda client: client.guilds.get_widget_image(2, style=WidgetStyle.BANNER2),
        method="GET",
        path=f"{G}/widget.png?style=banner2",
        response=PNG,
        result=base64.b64encode(PNG).decode(),  # bytes re-encode to JSON as base64
    ),
    EndpointCase(
        name="welcome screen",
        call=lambda client: client.guilds.get_welcome_screen(2),
        method="GET",
        path=f"{G}/welcome-screen",
        response=WELCOME,
    ),
    EndpointCase(
        name="modify welcome screen",
        call=lambda client: client.guilds.edit_welcome_screen(
            2,
            EditWelcomeScreenParams(
                enabled=True,
                welcome_channels=[
                    WelcomeScreenChannel(
                        channel_id=Snowflake(3), description="Say hi", emoji_id=None, emoji_name=None
                    )
                ],
            ),
        ),
        method="PATCH",
        path=f"{G}/welcome-screen",
        body={
            "enabled": True,
            "welcome_channels": [
                {"channel_id": "3", "description": "Say hi", "emoji_id": None, "emoji_name": None}
            ],
        },
        response=WELCOME,
    ),
    EndpointCase(
        name="onboarding",
        call=lambda client: client.guilds.get_onboarding(2),
        method="GET",
        path=f"{G}/onboarding",
        response=ONBOARDING,
    ),
    EndpointCase(
        name="modify onboarding",
        call=lambda client: client.guilds.edit_onboarding(
            2,
            EditOnboardingParams(
                prompts=[
                    OnboardingPromptParams(
                        id=Snowflake(1067461047608422473),
                        type=PromptType.DROPDOWN,
                        options=[
                            PromptOptionParams(
                                id=Snowflake(1070004843541954678),
                                channel_ids=[],
                                role_ids=[Snowflake(5)],
                                emoji_name="\N{GRINNING FACE}",
                                title="Get Gud",
                                description=None,
                            )
                        ],
                        title="Why are you here?",
                        single_select=True,
                        required=True,
                        in_onboarding=True,
                    )
                ],
                mode=OnboardingMode.ONBOARDING_ADVANCED,
            ),
        ),
        method="PUT",
        path=f"{G}/onboarding",
        body={
            "prompts": [
                {
                    "id": "1067461047608422473",
                    "type": 1,
                    "options": [
                        {
                            "id": "1070004843541954678",
                            "channel_ids": [],
                            "role_ids": ["5"],
                            "emoji_name": "\N{GRINNING FACE}",
                            "title": "Get Gud",
                            "description": None,
                        }
                    ],
                    "title": "Why are you here?",
                    "single_select": True,
                    "required": True,
                    "in_onboarding": True,
                }
            ],
            "mode": 1,
        },
        response=ONBOARDING,
    ),
    EndpointCase(
        name="incident actions",
        call=lambda client: client.guilds.edit_incident_actions(
            2,
            EditIncidentActionsParams(
                invites_disabled_until=datetime(2026, 1, 1, 12, tzinfo=UTC), dms_disabled_until=None
            ),
        ),
        method="PUT",
        path=f"{G}/incident-actions",
        body={"invites_disabled_until": "2026-01-01T12:00:00Z", "dms_disabled_until": None},
        response=INCIDENTS,
    ),
]


@endpoint_cases(CASES)
async def test_guild_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
