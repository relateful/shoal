"""Endpoints for guild scheduled events.

Discord: https://docs.discord.com/developers/resources/guild-scheduled-event
"""

import builtins

from shoal.payloads.scheduled_event import (
    CreateScheduledEventParams,
    EditScheduledEventParams,
    GuildScheduledEvent,
    GuildScheduledEventUser,
    ListScheduledEventUsersParams,
)
from shoal.rest.endpoints import (
    CREATE_GUILD_SCHEDULED_EVENT,
    DELETE_GUILD_SCHEDULED_EVENT,
    GET_GUILD_SCHEDULED_EVENT,
    GET_GUILD_SCHEDULED_EVENT_USERS,
    LIST_SCHEDULED_EVENTS_FOR_GUILD,
    MODIFY_GUILD_SCHEDULED_EVENT,
)
from shoal.rest.requester import Resource, query_of


class ScheduledEvents(Resource):
    """Guild scheduled events and their subscribers.

    Use it as `rest.scheduled_events`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def list(
        self, guild_id: int, *, with_user_count: bool = False
    ) -> builtins.list[GuildScheduledEvent]:
        """List a guild's scheduled events, optionally with subscriber counts.

        Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#list-scheduled-events-for-guild
        """
        return await self.request(
            LIST_SCHEDULED_EVENTS_FOR_GUILD.compile(guild_id=guild_id),
            list[GuildScheduledEvent],
            query={"with_user_count": True} if with_user_count else None,
        )

    async def create(
        self, guild_id: int, params: CreateScheduledEventParams, *, reason: str | None = None
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

    async def get(
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

    async def edit(
        self,
        guild_id: int,
        event_id: int,
        params: EditScheduledEventParams,
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

    async def delete(self, guild_id: int, event_id: int) -> None:
        """Delete a scheduled event.

        Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#delete-guild-scheduled-event
        """
        await self.request_empty(
            DELETE_GUILD_SCHEDULED_EVENT.compile(guild_id=guild_id, guild_scheduled_event_id=event_id)
        )

    async def list_users(
        self, guild_id: int, event_id: int, params: ListScheduledEventUsersParams | None = None
    ) -> builtins.list[GuildScheduledEventUser]:
        """List the users subscribed to a scheduled event, up to 100 at a time.

        Discord: https://docs.discord.com/developers/resources/guild-scheduled-event#get-guild-scheduled-event-users
        """
        return await self.request(
            GET_GUILD_SCHEDULED_EVENT_USERS.compile(guild_id=guild_id, guild_scheduled_event_id=event_id),
            list[GuildScheduledEventUser],
            query=query_of(params) if params is not None else None,
        )
