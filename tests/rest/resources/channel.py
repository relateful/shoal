from datetime import UTC, datetime

from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    AddRecipientParams,
    ChannelFlags,
    ChannelType,
    CreateInviteParams,
    CreatePostParams,
    CreateThreadFromMessageParams,
    CreateThreadParams,
    EditChannelPermissionsParams,
    EditGroupDMParams,
    EditGuildChannelParams,
    EditThreadParams,
    ForumTagParams,
    ForumThreadMessageParams,
    ListArchivedThreadsParams,
    ListJoinedPrivateArchivedThreadsParams,
    ListThreadMembersParams,
    OverwriteType,
    PartialOverwrite,
    Permissions,
)
from shoal.rest.files import File
from tests.support.json_payloads import (
    CHANNEL,
    INVITE,
    INVITE_WITH_METADATA,
    MESSAGE,
    THREAD,
    THREAD_MEMBER,
)
from tests.support.multipart import FormPart
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

FORUM: dict[str, object] = {
    "id": "15",
    "type": 15,
    "guild_id": "2",
    "name": "help",
    "available_tags": [
        {
            "id": "1",
            "name": "solved",
            "moderated": True,
            "emoji_id": None,
            "emoji_name": "\N{WHITE HEAVY CHECK MARK}",
        }
    ],
    "default_reaction_emoji": {"emoji_id": None, "emoji_name": "\N{THUMBS UP SIGN}"},
    "default_sort_order": None,
    "default_forum_layout": 1,
}
ARCHIVED: dict[str, object] = {"threads": [THREAD], "members": [THREAD_MEMBER], "has_more": False}
PNG = b"\x89PNG\r\n\x1a\n"

CASES = [
    EndpointCase(
        name="get channel",
        call=lambda client: client.channels.get(3),
        method="GET",
        path="/channels/3",
        response=CHANNEL,
    ),
    EndpointCase(
        name="channel member permissions",
        call=lambda client: client.channels.get_member_permissions(3, 5),
        method="GET",
        path="/channels/3/permissions/member/5",
        response={"permissions": "1024"},
        result="1024",
    ),
    EndpointCase(
        name="channel member permissions without implicit masking",
        call=lambda client: client.channels.get_member_permissions(3, 5, implicit=False),
        method="GET",
        path="/channels/3/permissions/member/5?implicit=false",
        response={"permissions": "0"},
        result="0",
    ),
    EndpointCase(
        name="channel role permissions",
        call=lambda client: client.channels.get_role_permissions(3, 6),
        method="GET",
        path="/channels/3/permissions/role/6",
        response={"permissions": "3072"},
        result="3072",
    ),
    EndpointCase(
        name="channel role permissions without implicit masking",
        call=lambda client: client.channels.get_role_permissions(3, 6, implicit=False),
        method="GET",
        path="/channels/3/permissions/role/6?implicit=false",
        response={"permissions": "2048"},
        result="2048",
    ),
    EndpointCase(
        name="modify guild channel",
        call=lambda client: client.channels.edit(
            15,
            EditGuildChannelParams(
                topic=None,
                permission_overwrites=[
                    PartialOverwrite(
                        id=Snowflake(2), type=OverwriteType.ROLE, deny=Permissions(send_messages=True)
                    )
                ],
                available_tags=[ForumTagParams(name="solved", moderated=True)],
            ),
            reason="tidy up",
        ),
        method="PATCH",
        path="/channels/15",
        body={
            "topic": None,
            "permission_overwrites": [{"id": "2", "type": 0, "deny": "2048"}],
            "available_tags": [{"name": "solved", "moderated": True}],
        },
        response=FORUM,
        reason="tidy up",
    ),
    EndpointCase(
        name="modify thread",
        call=lambda client: client.channels.edit(
            41771983423143937, EditThreadParams(archived=True, flags=ChannelFlags(pinned=True))
        ),
        method="PATCH",
        path="/channels/41771983423143937",
        body={"archived": True, "flags": 2},
        response=THREAD,
    ),
    EndpointCase(
        name="modify group dm",
        call=lambda client: client.channels.edit(4, EditGroupDMParams(name="friends")),
        method="PATCH",
        path="/channels/4",
        body={"name": "friends"},
        response={"id": "4", "type": 3, "name": "friends"},
    ),
    EndpointCase(
        name="set voice status",
        call=lambda client: client.channels.edit_voice_status(6, None),
        method="PUT",
        path="/channels/6/voice-status",
        body={"status": None},
    ),
    EndpointCase(
        name="delete channel",
        call=lambda client: client.channels.delete(3, reason="unused"),
        method="DELETE",
        path="/channels/3",
        response=CHANNEL,
        reason="unused",
    ),
    EndpointCase(
        name="edit permissions",
        call=lambda client: client.channels.edit_permissions(
            3,
            1,
            EditChannelPermissionsParams(allow=Permissions(view_channel=True), type=OverwriteType.MEMBER),
        ),
        method="PUT",
        path="/channels/3/permissions/1",
        body={"allow": "1024", "type": 1},
    ),
    EndpointCase(
        name="delete permission",
        call=lambda client: client.channels.delete_permissions(3, 1, reason="reset"),
        method="DELETE",
        path="/channels/3/permissions/1",
        reason="reset",
    ),
    EndpointCase(
        name="get invites",
        call=lambda client: client.invites.list_for_channel(3),
        method="GET",
        path="/channels/3/invites",
        response=[INVITE_WITH_METADATA],
    ),
    EndpointCase(
        name="create invite with defaults",
        call=lambda client: client.invites.create(3),
        method="POST",
        path="/channels/3/invites",
        body={},
        response=INVITE,
    ),
    EndpointCase(
        name="create invite for some users",
        call=lambda client: client.invites.create(
            3, CreateInviteParams(max_age=0, unique=True, target_user_ids=[Snowflake(1)])
        ),
        method="POST",
        path="/channels/3/invites",
        body={"max_age": 0, "unique": True, "target_user_ids": ["1"]},
        response=INVITE,
    ),
    EndpointCase(
        name="follow announcements",
        call=lambda client: client.channels.follow(5, 3),
        method="POST",
        path="/channels/5/followers",
        body={"webhook_channel_id": "3"},
        response={"channel_id": "5", "webhook_id": "8"},
    ),
    EndpointCase(
        name="typing",
        call=lambda client: client.channels.typing(3),
        method="POST",
        path="/channels/3/typing",
    ),
    EndpointCase(
        name="add group dm recipient",
        call=lambda client: client.channels.add_recipient(
            4, 1, AddRecipientParams(access_token="token", nick="Ada")
        ),
        method="PUT",
        path="/channels/4/recipients/1",
        body={"access_token": "token", "nick": "Ada"},
    ),
    EndpointCase(
        name="remove group dm recipient",
        call=lambda client: client.channels.remove_recipient(4, 1),
        method="DELETE",
        path="/channels/4/recipients/1",
    ),
    EndpointCase(
        name="thread from message",
        call=lambda client: client.threads.create_from_message(
            3, 9, CreateThreadFromMessageParams(name="discuss", auto_archive_duration=1440)
        ),
        method="POST",
        path="/channels/3/messages/9/threads",
        body={"name": "discuss", "auto_archive_duration": 1440},
        response=THREAD,
    ),
    EndpointCase(
        name="thread without message",
        call=lambda client: client.threads.create(
            3,
            CreateThreadParams(name="private", type=ChannelType.PRIVATE_THREAD, invitable=False),
        ),
        method="POST",
        path="/channels/3/threads",
        body={"name": "private", "type": 12, "invitable": False},
        response=THREAD,
    ),
    EndpointCase(
        name="forum post",
        call=lambda client: client.threads.create_post(
            15,
            CreatePostParams(
                name="It crashes",
                message=ForumThreadMessageParams(content="see the log"),
                applied_tags=[Snowflake(1)],
            ),
        ),
        method="POST",
        path="/channels/15/threads",
        body={"name": "It crashes", "message": {"content": "see the log"}, "applied_tags": ["1"]},
        response={**THREAD, "message": MESSAGE},
    ),
    EndpointCase(
        name="forum post with a file",
        call=lambda client: client.threads.create_post(
            15,
            CreatePostParams(name="Screenshot", message=ForumThreadMessageParams(content="look")),
            files=[File("shot.png", PNG, description="the error", content_type="image/png")],
        ),
        method="POST",
        path="/channels/15/threads",
        body={
            "name": "Screenshot",
            "message": {
                "content": "look",
                "attachments": [{"id": 0, "filename": "shot.png", "description": "the error"}],
            },
        },
        files=(FormPart("files[0]", "shot.png", "image/png", PNG),),
        response={**THREAD, "message": MESSAGE},
    ),
    EndpointCase(
        name="join thread",
        call=lambda client: client.threads.join(41771983423143937),
        method="PUT",
        path="/channels/41771983423143937/thread-members/@me",
    ),
    EndpointCase(
        name="add thread member",
        call=lambda client: client.threads.add_member(41771983423143937, 1),
        method="PUT",
        path="/channels/41771983423143937/thread-members/1",
    ),
    EndpointCase(
        name="leave thread",
        call=lambda client: client.threads.leave(41771983423143937),
        method="DELETE",
        path="/channels/41771983423143937/thread-members/@me",
    ),
    EndpointCase(
        name="remove thread member",
        call=lambda client: client.threads.remove_member(41771983423143937, 1),
        method="DELETE",
        path="/channels/41771983423143937/thread-members/1",
    ),
    EndpointCase(
        name="get thread member",
        call=lambda client: client.threads.get_member(41771983423143937, 1, with_member=True),
        method="GET",
        path="/channels/41771983423143937/thread-members/1?with_member=true",
        response=THREAD_MEMBER,
    ),
    EndpointCase(
        name="list thread members",
        call=lambda client: client.threads.list_members(
            41771983423143937, ListThreadMembersParams(with_member=True, after=Snowflake(1), limit=50)
        ),
        method="GET",
        path="/channels/41771983423143937/thread-members?with_member=true&after=1&limit=50",
        response=[THREAD_MEMBER],
    ),
    EndpointCase(
        name="public archived threads",
        call=lambda client: client.threads.list_public_archived(
            3, ListArchivedThreadsParams(before=datetime(2026, 1, 1, tzinfo=UTC), limit=2)
        ),
        method="GET",
        path="/channels/3/threads/archived/public?before=2026-01-01T00%3A00%3A00%2B00%3A00&limit=2",
        response=ARCHIVED,
    ),
    EndpointCase(
        name="private archived threads",
        call=lambda client: client.threads.list_private_archived(3),
        method="GET",
        path="/channels/3/threads/archived/private",
        response=ARCHIVED,
    ),
    EndpointCase(
        name="joined private archived threads",
        call=lambda client: client.threads.list_joined_private_archived(
            3, ListJoinedPrivateArchivedThreadsParams(before=Snowflake(41771983423143937))
        ),
        method="GET",
        path="/channels/3/users/@me/threads/archived/private?before=41771983423143937",
        response=ARCHIVED,
    ),
]


@endpoint_cases(CASES)
async def test_channel_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
