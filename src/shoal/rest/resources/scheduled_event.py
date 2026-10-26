"""Endpoints for guild scheduled events.

Discord: https://docs.discord.com/developers/resources/guild-scheduled-event
"""

from shoal.payloads.scheduled_event import (
    CreateGuildScheduledEventParams,
    GetGuildScheduledEventUsersParams,
    GuildScheduledEvent,
    GuildScheduledEventUser,
    ModifyGuildScheduledEventParams,
)
from shoal.rest.endpoints import (
    CREATE_GUILD_SCHEDULED_EVENT,
    DELETE_GUILD_SCHEDULED_EVENT,
    GET_GUILD_SCHEDULED_EVENT,
    GET_GUILD_SCHEDULED_EVENT_USERS,
    LIST_SCHEDULED_EVENTS_FOR_GUILD,
    MODIFY_GUILD_SCHEDULED_EVENT,
)
from shoal.rest.requester import Requester, query_of


class ScheduledEventEndpoints(Requester):
    """Endpoints for guild scheduled events; part of `RestClient`.

    The permissions needed depend on where the event happens; Discord lists them per entity type.
    """

    __slots__ = ()

    async def list_scheduled_events_for_guild(
        self, guild_id: int, *, with_user_count: bool = False
    ) -> list[GuildScheduledEvent]:
        """List a guild's scheduled events, optionally with subscriber counts.

        Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#list-scheduled-events-for-guild
        """
        return await self.request(
            LIST_SCHEDULED_EVENTS_FOR_GUILD.compile(guild_id=guild_id),
            list[GuildScheduledEvent],
            query={"with_user_count": True} if with_user_count else None,
        )

    async def create_guild_scheduled_event(
        self, guild_id: int, params: CreateGuildScheduledEventParams, *, reason: str | None = None
    ) -> GuildScheduledEvent:
        """Schedule an event. Needs Create Events, and channel permissions for stage and voice events.

        Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#create-guild-scheduled-event
        """
        return await self.request(
            CREATE_GUILD_SCHEDULED_EVENT.compile(guild_id=guild_id),
            GuildScheduledEvent,
            body=params,
            reason=reason,
        )

    async def get_guild_scheduled_event(
        self, guild_id: int, event_id: int, *, with_user_count: bool = False
    ) -> GuildScheduledEvent:
        """Get one scheduled event, optionally with its subscriber count.

        Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#get-guild-scheduled-event
        """
        return await self.request(
            GET_GUILD_SCHEDULED_EVENT.compile(guild_id=guild_id, guild_scheduled_event_id=event_id),
            GuildScheduledEvent,
            query={"with_user_count": True} if with_user_count else None,
        )

    async def modify_guild_scheduled_event(
        self,
        guild_id: int,
        event_id: int,
        params: ModifyGuildScheduledEventParams,
        *,
        reason: str | None = None,
    ) -> GuildScheduledEvent:
        """Change a scheduled event, or start or end it through `status`.

        Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#modify-guild-scheduled-event
        """
        return await self.request(
            MODIFY_GUILD_SCHEDULED_EVENT.compile(guild_id=guild_id, guild_scheduled_event_id=event_id),
            GuildScheduledEvent,
            body=params,
            reason=reason,
        )

    async def delete_guild_scheduled_event(self, guild_id: int, event_id: int) -> None:
        """Delete a scheduled event.

        Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#delete-guild-scheduled-event
        """
        await self.request_empty(
            DELETE_GUILD_SCHEDULED_EVENT.compile(guild_id=guild_id, guild_scheduled_event_id=event_id)
        )

    async def get_guild_scheduled_event_users(
        self, guild_id: int, event_id: int, params: GetGuildScheduledEventUsersParams | None = None
    ) -> list[GuildScheduledEventUser]:
        """List the users subscribed to a scheduled event, up to 100 at a time.

        Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#get-guild-scheduled-event-users
        """
        return await self.request(
            GET_GUILD_SCHEDULED_EVENT_USERS.compile(guild_id=guild_id, guild_scheduled_event_id=event_id),
            list[GuildScheduledEventUser],
            query=query_of(params) if params is not None else None,
        )
