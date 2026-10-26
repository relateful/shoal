"""Endpoints for channels, permission overwrites, invites to a channel, and threads.

Discord: https://docs.discord.com/developers/resources/channel
"""

from collections.abc import Sequence

import msgspec

from shoal.core.snowflake import Snowflake
from shoal.payloads.channel import (
    ArchivedThreads,
    Channel,
    EditChannelPermissionsParams,
    FollowAnnouncementChannelParams,
    FollowedChannel,
    GroupDMAddRecipientParams,
    ListArchivedThreadsParams,
    ListJoinedPrivateArchivedThreadsParams,
    ListThreadMembersParams,
    ModifyGroupDMParams,
    ModifyGuildChannelParams,
    ModifyThreadParams,
    SetVoiceChannelStatusParams,
    StartThreadFromMessageParams,
    StartThreadWithoutMessageParams,
    ThreadMember,
)
from shoal.payloads.forum import ForumThread, StartThreadInForumParams
from shoal.payloads.invite import CreateChannelInviteParams, Invite, InviteWithMetadata
from shoal.rest.endpoints import (
    ADD_THREAD_MEMBER,
    CREATE_CHANNEL_INVITE,
    DELETE_CHANNEL,
    DELETE_CHANNEL_PERMISSION,
    EDIT_CHANNEL_PERMISSIONS,
    FOLLOW_ANNOUNCEMENT_CHANNEL,
    GET_CHANNEL,
    GET_CHANNEL_INVITES,
    GET_THREAD_MEMBER,
    GROUP_DM_ADD_RECIPIENT,
    GROUP_DM_REMOVE_RECIPIENT,
    JOIN_THREAD,
    LEAVE_THREAD,
    LIST_JOINED_PRIVATE_ARCHIVED_THREADS,
    LIST_PRIVATE_ARCHIVED_THREADS,
    LIST_PUBLIC_ARCHIVED_THREADS,
    LIST_THREAD_MEMBERS,
    MODIFY_CHANNEL,
    REMOVE_THREAD_MEMBER,
    SET_VOICE_CHANNEL_STATUS,
    START_THREAD_FROM_MESSAGE,
    START_THREAD_IN_FORUM_OR_MEDIA_CHANNEL,
    START_THREAD_WITHOUT_MESSAGE,
    TRIGGER_TYPING_INDICATOR,
)
from shoal.rest.files import File
from shoal.rest.requester import Requester, query_of, with_attachments


class ChannelEndpoints(Requester):
    """Endpoints for channels, overwrites, channel invites and threads; part of `RestClient`."""

    __slots__ = ()

    async def get_channel(self, channel_id: int) -> Channel:
        """Get a channel or thread by ID. A thread includes the current user's `member`, if joined.

        Discord: https://docs.discord.com/developers/resources/channel#get-channel
        """
        return await self.request(GET_CHANNEL.compile(channel_id=channel_id), Channel)

    async def modify_channel(
        self,
        channel_id: int,
        params: ModifyGuildChannelParams | ModifyThreadParams | ModifyGroupDMParams,
        *,
        reason: str | None = None,
    ) -> Channel:
        """Change a guild channel, a thread or a group DM; each takes its own parameters.

        Discord: https://docs.discord.com/developers/resources/channel#modify-channel
        """
        return await self.request(
            MODIFY_CHANNEL.compile(channel_id=channel_id), Channel, body=params, reason=reason
        )

    async def set_voice_channel_status(
        self, channel_id: int, status: str | None, *, reason: str | None = None
    ) -> None:
        """Set or clear (`None`) a voice channel's status, up to 500 characters.

        Needs Set Voice Channel Status, and Manage Channels when not connected to the channel.

        Discord: https://docs.discord.com/developers/resources/channel#set-voice-channel-status
        """
        await self.request_empty(
            SET_VOICE_CHANNEL_STATUS.compile(channel_id=channel_id),
            body=SetVoiceChannelStatusParams(status=status),
            reason=reason,
        )

    async def delete_channel(self, channel_id: int, *, reason: str | None = None) -> Channel:
        """Delete a guild channel or thread for good, or close a DM.

        A deleted category's channels are kept, without a parent. Needs Manage Channels, or Manage
        Threads for a thread.

        Discord: https://docs.discord.com/developers/resources/channel#delete/close-channel
        """
        return await self.request(DELETE_CHANNEL.compile(channel_id=channel_id), Channel, reason=reason)

    async def edit_channel_permissions(
        self,
        channel_id: int,
        overwrite_id: int,
        params: EditChannelPermissionsParams,
        *,
        reason: str | None = None,
    ) -> None:
        """Set the overwrite for a role or member. Needs Manage Roles.

        Only permissions the bot has can be allowed or denied, unless it has a Manage Roles
        overwrite in the channel.

        Discord: https://docs.discord.com/developers/resources/channel#edit-channel-permissions
        """
        await self.request_empty(
            EDIT_CHANNEL_PERMISSIONS.compile(channel_id=channel_id, overwrite_id=overwrite_id),
            body=params,
            reason=reason,
        )

    async def delete_channel_permission(
        self, channel_id: int, overwrite_id: int, *, reason: str | None = None
    ) -> None:
        """Remove the overwrite for a role or member. Needs Manage Roles.

        Discord: https://docs.discord.com/developers/resources/channel#delete-channel-permission
        """
        await self.request_empty(
            DELETE_CHANNEL_PERMISSION.compile(channel_id=channel_id, overwrite_id=overwrite_id), reason=reason
        )

    async def get_channel_invites(self, channel_id: int) -> list[InviteWithMetadata]:
        """List a guild channel's invites. Needs Manage Channels.

        Discord: https://docs.discord.com/developers/resources/channel#get-channel-invites
        """
        return await self.request(
            GET_CHANNEL_INVITES.compile(channel_id=channel_id), list[InviteWithMetadata]
        )

    async def create_channel_invite(
        self,
        channel_id: int,
        params: CreateChannelInviteParams | None = None,
        *,
        reason: str | None = None,
    ) -> Invite:
        """Create an invite to a guild channel. Needs Create Instant Invite.

        Discord: https://docs.discord.com/developers/resources/channel#create-channel-invite
        """
        return await self.request(
            CREATE_CHANNEL_INVITE.compile(channel_id=channel_id),
            Invite,
            body=params or CreateChannelInviteParams(),
            reason=reason,
        )

    async def follow_announcement_channel(
        self, channel_id: int, webhook_channel_id: int, *, reason: str | None = None
    ) -> FollowedChannel:
        """Post an announcement channel's messages in another channel. Needs Manage Webhooks there.

        Discord: https://docs.discord.com/developers/resources/channel#follow-announcement-channel
        """
        return await self.request(
            FOLLOW_ANNOUNCEMENT_CHANNEL.compile(channel_id=channel_id),
            FollowedChannel,
            body=FollowAnnouncementChannelParams(webhook_channel_id=Snowflake(webhook_channel_id)),
            reason=reason,
        )

    async def trigger_typing_indicator(self, channel_id: int) -> None:
        """Show the bot as typing for 10 seconds, while a reply takes a few seconds to prepare.

        Discord: https://docs.discord.com/developers/resources/channel#trigger-typing-indicator
        """
        await self.request_empty(TRIGGER_TYPING_INDICATOR.compile(channel_id=channel_id))

    async def group_dm_add_recipient(
        self, channel_id: int, user_id: int, params: GroupDMAddRecipientParams
    ) -> None:
        """Add a user who granted the app `gdm.join` to a group DM.

        Discord: https://docs.discord.com/developers/resources/channel#group-dm-add-recipient
        """
        await self.request_empty(
            GROUP_DM_ADD_RECIPIENT.compile(channel_id=channel_id, user_id=user_id), body=params
        )

    async def group_dm_remove_recipient(self, channel_id: int, user_id: int) -> None:
        """Remove a user from a group DM.

        Discord: https://docs.discord.com/developers/resources/channel#group-dm-remove-recipient
        """
        await self.request_empty(GROUP_DM_REMOVE_RECIPIENT.compile(channel_id=channel_id, user_id=user_id))

    async def start_thread_from_message(
        self,
        channel_id: int,
        message_id: int,
        params: StartThreadFromMessageParams,
        *,
        reason: str | None = None,
    ) -> Channel:
        """Start a thread on a message; the thread gets the message's ID, so a message has at most one.

        Not for forum or media channels.

        Discord: https://docs.discord.com/developers/resources/channel#start-thread-from-message
        """
        return await self.request(
            START_THREAD_FROM_MESSAGE.compile(channel_id=channel_id, message_id=message_id),
            Channel,
            body=params,
            reason=reason,
        )

    async def start_thread_without_message(
        self, channel_id: int, params: StartThreadWithoutMessageParams, *, reason: str | None = None
    ) -> Channel:
        """Start a thread that is not attached to a message.

        Discord: https://docs.discord.com/developers/resources/channel#start-thread-without-message
        """
        return await self.request(
            START_THREAD_WITHOUT_MESSAGE.compile(channel_id=channel_id), Channel, body=params, reason=reason
        )

    async def start_thread_in_forum_or_media_channel(
        self,
        channel_id: int,
        params: StartThreadInForumParams,
        *,
        files: Sequence[File] = (),
        reason: str | None = None,
    ) -> ForumThread:
        """Create a post in a forum or media channel: a thread and its first message.

        Needs Send Messages.

        Discord: https://docs.discord.com/developers/resources/channel#start-thread-in-forum-or-media-channel
        """
        message, named = with_attachments(params.message, files)
        return await self.request(
            START_THREAD_IN_FORUM_OR_MEDIA_CHANNEL.compile(channel_id=channel_id),
            ForumThread,
            body=msgspec.structs.replace(params, message=message),
            files=named,
            reason=reason,
        )

    async def join_thread(self, channel_id: int) -> None:
        """Join an unarchived thread.

        Discord: https://docs.discord.com/developers/resources/channel#join-thread
        """
        await self.request_empty(JOIN_THREAD.compile(channel_id=channel_id))

    async def add_thread_member(self, channel_id: int, user_id: int) -> None:
        """Add a member to an unarchived thread. Needs permission to send messages in it.

        Discord: https://docs.discord.com/developers/resources/channel#add-thread-member
        """
        await self.request_empty(ADD_THREAD_MEMBER.compile(channel_id=channel_id, user_id=user_id))

    async def leave_thread(self, channel_id: int) -> None:
        """Leave an unarchived thread.

        Discord: https://docs.discord.com/developers/resources/channel#leave-thread
        """
        await self.request_empty(LEAVE_THREAD.compile(channel_id=channel_id))

    async def remove_thread_member(self, channel_id: int, user_id: int) -> None:
        """Remove a member from an unarchived thread.

        Needs Manage Threads, or to be the creator of a private thread.

        Discord: https://docs.discord.com/developers/resources/channel#remove-thread-member
        """
        await self.request_empty(REMOVE_THREAD_MEMBER.compile(channel_id=channel_id, user_id=user_id))

    async def get_thread_member(
        self, channel_id: int, user_id: int, *, with_member: bool = False
    ) -> ThreadMember:
        """Get one member of a thread; `with_member` adds their guild member.

        Raises:
            NotFoundError: The user is not in the thread.

        Discord: https://docs.discord.com/developers/resources/channel#get-thread-member
        """
        return await self.request(
            GET_THREAD_MEMBER.compile(channel_id=channel_id, user_id=user_id),
            ThreadMember,
            query={"with_member": True} if with_member else None,
        )

    async def list_thread_members(
        self, channel_id: int, params: ListThreadMembersParams | None = None
    ) -> list[ThreadMember]:
        """List a thread's members. Needs the Guild Members privileged intent enabled for the app.

        With `with_member`, results come in pages of up to 100, after `after`.

        Discord: https://docs.discord.com/developers/resources/channel#list-thread-members
        """
        return await self.request(
            LIST_THREAD_MEMBERS.compile(channel_id=channel_id),
            list[ThreadMember],
            query=query_of(params) if params is not None else None,
        )

    async def list_public_archived_threads(
        self, channel_id: int, params: ListArchivedThreadsParams | None = None
    ) -> ArchivedThreads:
        """List a channel's archived public threads, most recently archived first.

        Needs Read Message History.

        Discord: https://docs.discord.com/developers/resources/channel#list-public-archived-threads
        """
        return await self.request(
            LIST_PUBLIC_ARCHIVED_THREADS.compile(channel_id=channel_id),
            ArchivedThreads,
            query=query_of(params) if params is not None else None,
        )

    async def list_private_archived_threads(
        self, channel_id: int, params: ListArchivedThreadsParams | None = None
    ) -> ArchivedThreads:
        """List a channel's archived private threads, most recently archived first.

        Needs Read Message History and Manage Threads.

        Discord: https://docs.discord.com/developers/resources/channel#list-private-archived-threads
        """
        return await self.request(
            LIST_PRIVATE_ARCHIVED_THREADS.compile(channel_id=channel_id),
            ArchivedThreads,
            query=query_of(params) if params is not None else None,
        )

    async def list_joined_private_archived_threads(
        self, channel_id: int, params: ListJoinedPrivateArchivedThreadsParams | None = None
    ) -> ArchivedThreads:
        """List the archived private threads the current user joined, newest ID first.

        Needs Read Message History.

        Discord: https://docs.discord.com/developers/resources/channel#list-joined-private-archived-threads
        """
        return await self.request(
            LIST_JOINED_PRIVATE_ARCHIVED_THREADS.compile(channel_id=channel_id),
            ArchivedThreads,
            query=query_of(params) if params is not None else None,
        )
