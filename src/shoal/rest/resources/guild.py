"""Endpoints for guilds, their members, bans and roles, prune, integrations and widgets.

Discord: https://docs.discord.com/developers/resources/guild
"""

import builtins
from collections.abc import Sequence

from shoal.core.snowflake import Snowflake
from shoal.payloads.guild import (
    AddMemberParams,
    Ban,
    BanParams,
    BulkBanParams,
    BulkBanResponse,
    CreateRoleParams,
    EditCurrentMemberParams,
    EditCurrentNickParams,
    EditGuildParams,
    EditIncidentActionsParams,
    EditMemberParams,
    EditOnboardingParams,
    EditRoleParams,
    EditWelcomeScreenParams,
    EditWidgetParams,
    GetPruneCountParams,
    Guild,
    GuildMember,
    GuildOnboarding,
    GuildPreview,
    GuildWidget,
    GuildWidgetSettings,
    IncidentsData,
    Integration,
    ListBansParams,
    ListMembersParams,
    PartialGuild,
    PruneCount,
    PruneParams,
    RolePositionParams,
    SearchMembersParams,
    WelcomeScreen,
    WidgetStyle,
)
from shoal.payloads.invite import VanityURL
from shoal.payloads.permissions import Role
from shoal.payloads.user import (
    ListGuildsParams,
)
from shoal.payloads.voice import VoiceRegion
from shoal.rest.endpoints import (
    ADD_GUILD_MEMBER,
    ADD_GUILD_MEMBER_ROLE,
    BEGIN_GUILD_PRUNE,
    BULK_GUILD_BAN,
    CREATE_GUILD_BAN,
    CREATE_GUILD_ROLE,
    DELETE_GUILD_INTEGRATION,
    DELETE_GUILD_ROLE,
    GET_CURRENT_USER_GUILD_MEMBER,
    GET_CURRENT_USER_GUILDS,
    GET_GUILD,
    GET_GUILD_BAN,
    GET_GUILD_BANS,
    GET_GUILD_INTEGRATIONS,
    GET_GUILD_MEMBER,
    GET_GUILD_ONBOARDING,
    GET_GUILD_PREVIEW,
    GET_GUILD_PRUNE_COUNT,
    GET_GUILD_ROLE,
    GET_GUILD_ROLE_MEMBER_COUNTS,
    GET_GUILD_ROLES,
    GET_GUILD_VANITY_URL,
    GET_GUILD_VOICE_REGIONS,
    GET_GUILD_WELCOME_SCREEN,
    GET_GUILD_WIDGET,
    GET_GUILD_WIDGET_IMAGE,
    GET_GUILD_WIDGET_SETTINGS,
    LEAVE_GUILD,
    LIST_GUILD_MEMBERS,
    MODIFY_CURRENT_MEMBER,
    MODIFY_CURRENT_USER_NICK,
    MODIFY_GUILD,
    MODIFY_GUILD_INCIDENT_ACTIONS,
    MODIFY_GUILD_MEMBER,
    MODIFY_GUILD_ONBOARDING,
    MODIFY_GUILD_ROLE,
    MODIFY_GUILD_ROLE_POSITIONS,
    MODIFY_GUILD_WELCOME_SCREEN,
    MODIFY_GUILD_WIDGET,
    REMOVE_GUILD_BAN,
    REMOVE_GUILD_MEMBER,
    REMOVE_GUILD_MEMBER_ROLE,
    SEARCH_GUILD_MEMBERS,
)
from shoal.rest.requester import Resource, comma_joined, query_of


class Guilds(Resource):
    """Guilds and their settings, widgets, onboarding and integrations.

    Use it as `rest.guilds`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def get(self, guild_id: int, *, with_counts: bool = False) -> Guild:
        """Get a guild, optionally with approximate member and presence counts.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild
        """
        return await self.request(
            GET_GUILD.compile(guild_id=guild_id), Guild, query={"with_counts": with_counts}
        )

    async def get_preview(self, guild_id: int) -> GuildPreview:
        """Get a guild's public preview; outside the guild it must be discoverable.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-preview
        """
        return await self.request(GET_GUILD_PREVIEW.compile(guild_id=guild_id), GuildPreview)

    async def edit(self, guild_id: int, params: EditGuildParams, *, reason: str | None = None) -> Guild:
        """Change a guild's settings. Needs Manage Guild.

        Discord: https://docs.discord.com/developers/resources/guild#modify-guild
        """
        return await self.request(MODIFY_GUILD.compile(guild_id=guild_id), Guild, body=params, reason=reason)

    async def get_prune_count(self, guild_id: int, params: GetPruneCountParams | None = None) -> PruneCount:
        """Count the members a prune would remove.

        Needs Manage Guild and Kick Members, or Administrator with the `PRUNE_REQUIRES_ADMIN` feature.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-prune-count
        """
        query = comma_joined(query_of(params), "include_roles") if params is not None else {}
        return await self.request(
            GET_GUILD_PRUNE_COUNT.compile(guild_id=guild_id), PruneCount, query=query or None
        )

    async def prune(
        self, guild_id: int, params: PruneParams | None = None, *, reason: str | None = None
    ) -> PruneCount:
        """Remove inactive members without roles (or only with `include_roles`).

        Needs Manage Guild and Kick Members, or Administrator with the `PRUNE_REQUIRES_ADMIN` feature.

        Discord: https://docs.discord.com/developers/resources/guild#begin-guild-prune
        """
        return await self.request(
            BEGIN_GUILD_PRUNE.compile(guild_id=guild_id),
            PruneCount,
            body=params or PruneParams(),
            reason=reason,
        )

    async def list_voice_regions(self, guild_id: int) -> builtins.list[VoiceRegion]:
        """List voice regions for the guild, including VIP regions when it has them.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-voice-regions
        """
        return await self.request(GET_GUILD_VOICE_REGIONS.compile(guild_id=guild_id), list[VoiceRegion])

    async def list_integrations(self, guild_id: int) -> builtins.list[Integration]:
        """List up to 50 integrations; any beyond cannot be read. Needs Manage Guild.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-integrations
        """
        return await self.request(GET_GUILD_INTEGRATIONS.compile(guild_id=guild_id), list[Integration])

    async def delete_integration(
        self, guild_id: int, integration_id: int, *, reason: str | None = None
    ) -> None:
        """Remove an integration, its webhooks and its bot. Needs Manage Guild.

        Discord: https://docs.discord.com/developers/resources/guild#delete-guild-integration
        """
        await self.request_empty(
            DELETE_GUILD_INTEGRATION.compile(guild_id=guild_id, integration_id=integration_id), reason=reason
        )

    async def get_widget_settings(self, guild_id: int) -> GuildWidgetSettings:
        """Get whether the widget is on, and its invite channel. Needs Manage Guild.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-widget-settings
        """
        return await self.request(GET_GUILD_WIDGET_SETTINGS.compile(guild_id=guild_id), GuildWidgetSettings)

    async def edit_widget(
        self, guild_id: int, params: EditWidgetParams, *, reason: str | None = None
    ) -> GuildWidgetSettings:
        """Turn the widget on or off, or change its invite channel. Needs Manage Guild.

        Discord: https://docs.discord.com/developers/resources/guild#modify-guild-widget
        """
        return await self.request(
            MODIFY_GUILD_WIDGET.compile(guild_id=guild_id), GuildWidgetSettings, body=params, reason=reason
        )

    async def get_widget(self, guild_id: int) -> GuildWidget:
        """Get the public widget.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-widget
        """
        return await self.request(GET_GUILD_WIDGET.compile(guild_id=guild_id), GuildWidget)

    async def get_vanity_url(self, guild_id: int) -> VanityURL:
        """Get the vanity invite and its use count. Needs Manage Guild.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-vanity-url
        """
        return await self.request(GET_GUILD_VANITY_URL.compile(guild_id=guild_id), VanityURL)

    async def get_widget_image(self, guild_id: int, *, style: WidgetStyle | None = None) -> bytes:
        """Get the widget as a PNG image. Needs no token.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-widget-image
        """
        return await self.request_bytes(
            GET_GUILD_WIDGET_IMAGE.compile(guild_id=guild_id),
            query={"style": style.value} if style is not None else None,
        )

    async def get_welcome_screen(self, guild_id: int) -> WelcomeScreen:
        """Get the welcome screen; when it is off, needs Manage Guild.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-welcome-screen
        """
        return await self.request(GET_GUILD_WELCOME_SCREEN.compile(guild_id=guild_id), WelcomeScreen)

    async def edit_welcome_screen(
        self, guild_id: int, params: EditWelcomeScreenParams, *, reason: str | None = None
    ) -> WelcomeScreen:
        """Change the welcome screen. Needs Manage Guild.

        Discord: https://docs.discord.com/developers/resources/guild#modify-guild-welcome-screen
        """
        return await self.request(
            MODIFY_GUILD_WELCOME_SCREEN.compile(guild_id=guild_id), WelcomeScreen, body=params, reason=reason
        )

    async def get_onboarding(self, guild_id: int) -> GuildOnboarding:
        """Get the onboarding flow.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-onboarding
        """
        return await self.request(GET_GUILD_ONBOARDING.compile(guild_id=guild_id), GuildOnboarding)

    async def edit_onboarding(
        self, guild_id: int, params: EditOnboardingParams, *, reason: str | None = None
    ) -> GuildOnboarding:
        """Change the onboarding flow. Needs Manage Guild and Manage Roles.

        Discord: https://docs.discord.com/developers/resources/guild#modify-guild-onboarding
        """
        return await self.request(
            MODIFY_GUILD_ONBOARDING.compile(guild_id=guild_id), GuildOnboarding, body=params, reason=reason
        )

    async def edit_incident_actions(self, guild_id: int, params: EditIncidentActionsParams) -> IncidentsData:
        """Pause invites or DMs for up to 24 hours, or end a pause. Needs Manage Guild.

        Discord: https://docs.discord.com/developers/resources/guild#modify-guild-incident-actions
        """
        return await self.request(
            MODIFY_GUILD_INCIDENT_ACTIONS.compile(guild_id=guild_id), IncidentsData, body=params
        )

    async def list(self, params: ListGuildsParams | None = None) -> builtins.list[PartialGuild]:
        """List the guilds the current user is in, up to 200 per call.

        Bots using large bot sharding must pass `shard` and call once per value.

        Discord: https://docs.discord.com/developers/resources/user#get-current-user-guilds
        """
        query = query_of(params) if params is not None else None
        return await self.request(GET_CURRENT_USER_GUILDS.compile(), list[PartialGuild], query=query)

    async def leave(self, guild_id: int) -> None:
        """Leave a guild.

        Discord: https://docs.discord.com/developers/resources/user#leave-guild
        """
        await self.request_empty(LEAVE_GUILD.compile(guild_id=guild_id))


class Members(Resource):
    """Guild members, their roles, and bans.

    Use it as `rest.members`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def get(self, guild_id: int, user_id: int) -> GuildMember:
        """Get one member of a guild.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-member
        """
        return await self.request(GET_GUILD_MEMBER.compile(guild_id=guild_id, user_id=user_id), GuildMember)

    async def list(
        self, guild_id: int, params: ListMembersParams | None = None
    ) -> builtins.list[GuildMember]:
        """List members by user ID, up to 1000 at a time. Needs the Guild Members privileged intent.

        Discord: https://docs.discord.com/developers/resources/guild#list-guild-members
        """
        return await self.request(
            LIST_GUILD_MEMBERS.compile(guild_id=guild_id),
            list[GuildMember],
            query=query_of(params) if params is not None else None,
        )

    async def search(self, guild_id: int, params: SearchMembersParams) -> builtins.list[GuildMember]:
        """Find members whose username or nickname starts with `params.query`.

        Discord: https://docs.discord.com/developers/resources/guild#search-guild-members
        """
        return await self.request(
            SEARCH_GUILD_MEMBERS.compile(guild_id=guild_id), list[GuildMember], query=query_of(params)
        )

    async def add(self, guild_id: int, user_id: int, params: AddMemberParams) -> GuildMember | None:
        """Add a user who granted the app `guilds.join`; `None` if they were already a member.

        Needs a bot token of that app, in the guild with Create Instant Invite.

        Discord: https://docs.discord.com/developers/resources/guild#add-guild-member
        """
        return await self.request_optional(
            ADD_GUILD_MEMBER.compile(guild_id=guild_id, user_id=user_id), GuildMember, body=params
        )

    async def edit(
        self, guild_id: int, user_id: int, params: EditMemberParams, *, reason: str | None = None
    ) -> GuildMember:
        """Change a member: nickname, roles, voice state and channel, timeout or flags.

        Discord: https://docs.discord.com/developers/resources/guild#modify-guild-member
        """
        return await self.request(
            MODIFY_GUILD_MEMBER.compile(guild_id=guild_id, user_id=user_id),
            GuildMember,
            body=params,
            reason=reason,
        )

    async def edit_me(
        self, guild_id: int, params: EditCurrentMemberParams, *, reason: str | None = None
    ) -> GuildMember:
        """Change the bot's own nickname, guild avatar, banner or bio.

        Discord: https://docs.discord.com/developers/resources/guild#modify-current-member
        """
        return await self.request(
            MODIFY_CURRENT_MEMBER.compile(guild_id=guild_id), GuildMember, body=params, reason=reason
        )

    async def edit_my_nick(self, guild_id: int, nick: str | None, *, reason: str | None = None) -> None:
        """Deprecated: use `edit_me`. Change the bot's nickname.

        Discord answers with the nickname, which this method does not decode.

        Discord: https://docs.discord.com/developers/resources/guild#modify-current-user-nick
        """
        await self.request_empty(
            MODIFY_CURRENT_USER_NICK.compile(guild_id=guild_id),
            body=EditCurrentNickParams(nick=nick),
            reason=reason,
        )

    async def add_role(self, guild_id: int, user_id: int, role_id: int, *, reason: str | None = None) -> None:
        """Give a member a role. Needs Manage Roles.

        Discord: https://docs.discord.com/developers/resources/guild#add-guild-member-role
        """
        await self.request_empty(
            ADD_GUILD_MEMBER_ROLE.compile(guild_id=guild_id, user_id=user_id, role_id=role_id), reason=reason
        )

    async def remove_role(
        self, guild_id: int, user_id: int, role_id: int, *, reason: str | None = None
    ) -> None:
        """Take a role from a member. Needs Manage Roles.

        Discord: https://docs.discord.com/developers/resources/guild#remove-guild-member-role
        """
        await self.request_empty(
            REMOVE_GUILD_MEMBER_ROLE.compile(guild_id=guild_id, user_id=user_id, role_id=role_id),
            reason=reason,
        )

    async def kick(self, guild_id: int, user_id: int, *, reason: str | None = None) -> None:
        """Kick a member. Needs Kick Members.

        Discord: https://docs.discord.com/developers/resources/guild#remove-guild-member
        """
        await self.request_empty(
            REMOVE_GUILD_MEMBER.compile(guild_id=guild_id, user_id=user_id), reason=reason
        )

    async def list_bans(self, guild_id: int, params: ListBansParams | None = None) -> builtins.list[Ban]:
        """List bans, up to 1000 at a time, by user ID. Needs Ban Members or View Audit Log.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-bans
        """
        return await self.request(
            GET_GUILD_BANS.compile(guild_id=guild_id),
            list[Ban],
            query=query_of(params) if params is not None else None,
        )

    async def get_ban(self, guild_id: int, user_id: int) -> Ban:
        """Get one ban. Needs Ban Members or View Audit Log.

        Raises:
            NotFoundError: The user is not banned.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-ban
        """
        return await self.request(GET_GUILD_BAN.compile(guild_id=guild_id, user_id=user_id), Ban)

    async def ban(
        self,
        guild_id: int,
        user_id: int,
        params: BanParams | None = None,
        *,
        reason: str | None = None,
    ) -> None:
        """Ban a user, optionally deleting their recent messages. Needs Ban Members.

        Discord: https://docs.discord.com/developers/resources/guild#create-guild-ban
        """
        await self.request_empty(
            CREATE_GUILD_BAN.compile(guild_id=guild_id, user_id=user_id), body=params, reason=reason
        )

    async def unban(self, guild_id: int, user_id: int, *, reason: str | None = None) -> None:
        """Lift a ban. Needs Ban Members.

        Discord: https://docs.discord.com/developers/resources/guild#remove-guild-ban
        """
        await self.request_empty(REMOVE_GUILD_BAN.compile(guild_id=guild_id, user_id=user_id), reason=reason)

    async def bulk_ban(
        self, guild_id: int, params: BulkBanParams, *, reason: str | None = None
    ) -> BulkBanResponse:
        """Ban up to 200 users at once. Needs Ban Members and Manage Guild.

        Raises:
            HTTPError: None of the users could be banned (Discord error 500000).

        Discord: https://docs.discord.com/developers/resources/guild#bulk-guild-ban
        """
        return await self.request(
            BULK_GUILD_BAN.compile(guild_id=guild_id), BulkBanResponse, body=params, reason=reason
        )

    async def get_me(self, guild_id: int) -> GuildMember:
        """Get the current user's membership in a guild. Needs the `guilds.members.read` scope.

        Discord: https://docs.discord.com/developers/resources/user#get-current-user-guild-member
        """
        return await self.request(GET_CURRENT_USER_GUILD_MEMBER.compile(guild_id=guild_id), GuildMember)


class Roles(Resource):
    """Guild roles.

    Use it as `rest.roles`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def list(self, guild_id: int) -> builtins.list[Role]:
        """List a guild's roles.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-roles
        """
        return await self.request(GET_GUILD_ROLES.compile(guild_id=guild_id), list[Role])

    async def get(self, guild_id: int, role_id: int) -> Role:
        """Get one role.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-role
        """
        return await self.request(GET_GUILD_ROLE.compile(guild_id=guild_id, role_id=role_id), Role)

    async def get_member_counts(self, guild_id: int) -> dict[Snowflake, int]:
        """Count the members of each role, by role ID; @everyone is left out.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-role-member-counts
        """
        return await self.request(
            GET_GUILD_ROLE_MEMBER_COUNTS.compile(guild_id=guild_id), dict[Snowflake, int]
        )

    async def create(
        self, guild_id: int, params: CreateRoleParams | None = None, *, reason: str | None = None
    ) -> Role:
        """Create a role. Needs Manage Roles.

        Discord: https://docs.discord.com/developers/resources/guild#create-guild-role
        """
        return await self.request(
            CREATE_GUILD_ROLE.compile(guild_id=guild_id),
            Role,
            body=params or CreateRoleParams(),
            reason=reason,
        )

    async def edit_positions(
        self, guild_id: int, positions: Sequence[RolePositionParams], *, reason: str | None = None
    ) -> builtins.list[Role]:
        """Reorder roles; returns every role in the guild. Needs Manage Roles.

        Discord: https://docs.discord.com/developers/resources/guild#modify-guild-role-positions
        """
        return await self.request(
            MODIFY_GUILD_ROLE_POSITIONS.compile(guild_id=guild_id),
            list[Role],
            body=list(positions),
            reason=reason,
        )

    async def edit(
        self, guild_id: int, role_id: int, params: EditRoleParams, *, reason: str | None = None
    ) -> Role:
        """Change a role. Needs Manage Roles.

        Discord: https://docs.discord.com/developers/resources/guild#modify-guild-role
        """
        return await self.request(
            MODIFY_GUILD_ROLE.compile(guild_id=guild_id, role_id=role_id), Role, body=params, reason=reason
        )

    async def delete(self, guild_id: int, role_id: int, *, reason: str | None = None) -> None:
        """Delete a role. Needs Manage Roles.

        Discord: https://docs.discord.com/developers/resources/guild#delete-guild-role
        """
        await self.request_empty(DELETE_GUILD_ROLE.compile(guild_id=guild_id, role_id=role_id), reason=reason)
