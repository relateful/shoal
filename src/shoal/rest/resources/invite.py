"""Endpoints for invites and the users an invite is limited to.

Discord: https://docs.discord.com/developers/resources/invite
"""

import builtins
import csv
import io
from collections.abc import Sequence

from shoal.core.codec import PayloadDecodeError
from shoal.core.snowflake import Snowflake
from shoal.payloads.invite import (
    CreateInviteParams,
    GetInviteParams,
    GuildInvite,
    Invite,
    InviteWithMetadata,
    TargetUserIDs,
    TargetUsersJobStatus,
)
from shoal.rest.endpoints import (
    ADD_TARGET_USER,
    BULK_ADD_TARGET_USERS,
    BULK_DELETE_TARGET_USERS,
    CREATE_CHANNEL_INVITE,
    DELETE_INVITE,
    GET_CHANNEL_INVITES,
    GET_GUILD_INVITES,
    GET_INVITE,
    GET_TARGET_USERS,
    GET_TARGET_USERS_JOB_STATUS,
    REMOVE_TARGET_USER,
    UPDATE_TARGET_USERS,
)
from shoal.rest.files import File
from shoal.rest.requester import Resource, query_of


def parse_target_users(body: bytes) -> list[Snowflake]:
    """Read the CSV Get Target Users answers with: a `user_id` header, then one ID per row.

    Raises:
        PayloadDecodeError: The body is not that CSV, so the list is never silently cut short.
    """
    try:
        rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error) as error:
        raise PayloadDecodeError(list[Snowflake], f"target users CSV: {error}") from None
    cells = [row[0].strip() for row in rows if row and row[0].strip()]
    if cells and cells[0] == "user_id":
        cells = cells[1:]
    if not all(cell.isascii() and cell.isdigit() for cell in cells):
        raise PayloadDecodeError(list[Snowflake], "target users CSV has a row that is not a user ID")
    return [Snowflake(cell) for cell in cells]


class Invites(Resource):
    """Invites and their target users.

    Use it as `rest.invites`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def list_for_channel(self, channel_id: int) -> builtins.list[InviteWithMetadata]:
        """List a guild channel's invites. Needs Manage Channels.

        Discord: https://docs.discord.com/developers/resources/channel#get-channel-invites
        """
        return await self.request(
            GET_CHANNEL_INVITES.compile(channel_id=channel_id), list[InviteWithMetadata]
        )

    async def create(
        self,
        channel_id: int,
        params: CreateInviteParams | None = None,
        *,
        reason: str | None = None,
    ) -> Invite:
        """Create an invite to a guild channel. Needs Create Instant Invite.

        Discord: https://docs.discord.com/developers/resources/channel#create-channel-invite
        """
        return await self.request(
            CREATE_CHANNEL_INVITE.compile(channel_id=channel_id),
            Invite,
            body=params or CreateInviteParams(),
            reason=reason,
        )

    async def list(self, guild_id: int) -> builtins.list[GuildInvite]:
        """List a guild's invites. Needs Manage Guild or View Audit Log.

        The usage fields are only there with Manage Guild.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-invites
        """
        return await self.request(GET_GUILD_INVITES.compile(guild_id=guild_id), list[GuildInvite])

    async def get(self, invite_code: str, params: GetInviteParams | None = None) -> Invite:
        """Get an invite by its code.

        Discord: https://docs.discord.com/developers/resources/invite#get-invite
        """
        return await self.request(
            GET_INVITE.compile(invite_code=invite_code),
            Invite,
            query=query_of(params) if params is not None else None,
        )

    async def delete(self, invite_code: str, *, reason: str | None = None) -> Invite:
        """Delete an invite. Needs Manage Channels on its channel, or Manage Guild.

        Discord: https://docs.discord.com/developers/resources/invite#delete-invite
        """
        return await self.request(DELETE_INVITE.compile(invite_code=invite_code), Invite, reason=reason)

    async def list_target_users(self, invite_code: str) -> builtins.list[Snowflake]:
        """List the only users who can see and accept an invite.

        Needs to be the inviter, or Manage Guild or View Audit Log.

        Raises:
            PayloadDecodeError: Discord's CSV could not be read.

        Discord: https://docs.discord.com/developers/resources/invite#get-target-users
        """
        body = await self.request_bytes(GET_TARGET_USERS.compile(invite_code=invite_code))
        return parse_target_users(body)

    async def add_target_user(self, invite_code: str, user_id: int) -> None:
        """Let one more user see and accept an invite. Needs to be the inviter, or Manage Guild.

        Discord: https://docs.discord.com/developers/resources/invite#add-target-user
        """
        await self.request_empty(ADD_TARGET_USER.compile(invite_code=invite_code, user_id=user_id))

    async def remove_target_user(self, invite_code: str, user_id: int) -> None:
        """Stop a user from seeing and accepting an invite. Needs to be the inviter, or Manage Guild.

        Discord: https://docs.discord.com/developers/resources/invite#remove-target-user
        """
        await self.request_empty(REMOVE_TARGET_USER.compile(invite_code=invite_code, user_id=user_id))

    async def overwrite_target_users(self, invite_code: str, user_ids: Sequence[int]) -> None:
        """Replace the users who can see and accept an invite, uploaded as a CSV file.

        Discord processes the file in the background; follow it with `get_target_users_status`.
        Needs to be the inviter, or Manage Guild.

        Discord: https://docs.discord.com/developers/resources/invite#update-target-users
        """
        csv = "".join(f"{int(user_id)}\n" for user_id in user_ids).encode()
        await self.request_empty(
            UPDATE_TARGET_USERS.compile(invite_code=invite_code),
            files={"target_users_file": File("target_users.csv", csv, content_type="text/csv")},
        )

    async def bulk_add_target_users(self, invite_code: str, user_ids: Sequence[int]) -> None:
        """Let up to 1000 more users see and accept an invite.

        Needs to be the inviter, or Manage Guild.

        Discord: https://docs.discord.com/developers/resources/invite#bulk-add-target-users
        """
        await self.request_empty(
            BULK_ADD_TARGET_USERS.compile(invite_code=invite_code),
            body=TargetUserIDs(user_ids=[Snowflake(user_id) for user_id in user_ids]),
        )

    async def bulk_remove_target_users(self, invite_code: str, user_ids: Sequence[int]) -> None:
        """Stop up to 1000 users from seeing and accepting an invite.

        Needs to be the inviter, or Manage Guild.

        Discord: https://docs.discord.com/developers/resources/invite#bulk-delete-target-users
        """
        await self.request_empty(
            BULK_DELETE_TARGET_USERS.compile(invite_code=invite_code),
            body=TargetUserIDs(user_ids=[Snowflake(user_id) for user_id in user_ids]),
        )

    async def get_target_users_status(self, invite_code: str) -> TargetUsersJobStatus:
        """See how far Discord has got with an uploaded target user list.

        Needs to be the inviter, or Manage Guild or View Audit Log.

        Discord: https://docs.discord.com/developers/resources/invite#get-target-users-job-status
        """
        return await self.request(
            GET_TARGET_USERS_JOB_STATUS.compile(invite_code=invite_code), TargetUsersJobStatus
        )
