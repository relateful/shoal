"""Endpoints for lobbies, used by a game's server alongside the Social SDK.

Some need a bot token and others a player's bearer token with the `sdk.social_layer` scope; each
method says which.

Discord: https://docs.discord.com/developers/resources/lobby
"""

from collections.abc import Mapping, Sequence

from shoal.core.snowflake import Snowflake
from shoal.payloads.lobby import (
    AddLobbyMemberParams,
    BulkLobbyMemberParams,
    CreateLobbyParams,
    CreateOrJoinLobbyParams,
    EditLobbyParams,
    LinkLobbyChannelParams,
    ListLobbyMessagesParams,
    Lobby,
    LobbyInvite,
    LobbyMember,
    LobbyMessage,
    SendLobbyMessageParams,
)
from shoal.rest.endpoints import (
    ADD_A_MEMBER_TO_A_LOBBY,
    BULK_UPDATE_LOBBY_MEMBERS,
    CREATE_LOBBY,
    CREATE_LOBBY_CHANNEL_INVITE_FOR_SELF,
    CREATE_LOBBY_CHANNEL_INVITE_FOR_USER,
    CREATE_OR_JOIN_LOBBY,
    DELETE_LOBBY,
    GET_LOBBY,
    GET_LOBBY_MESSAGES,
    LEAVE_LOBBY,
    LINK_CHANNEL_TO_LOBBY,
    MODIFY_LOBBY,
    REMOVE_A_MEMBER_FROM_A_LOBBY,
    SEND_LOBBY_MESSAGE,
    UNLINK_CHANNEL_FROM_LOBBY,
    UPDATE_LOBBY_MESSAGE_MODERATION_METADATA,
)
from shoal.rest.requester import Resource, query_of


class Lobbies(Resource):
    """Lobbies, their members and messages.

    Use it as `rest.lobbies`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def create(self, params: CreateLobbyParams | None = None) -> Lobby:
        """Create a lobby, with up to 25 members. Social SDK clients cannot join or leave it.

        Discord: https://docs.discord.com/developers/resources/lobby#create-lobby
        """
        return await self.request(CREATE_LOBBY.compile(), Lobby, body=params or CreateLobbyParams())

    async def create_or_join(self, params: CreateOrJoinLobbyParams) -> Lobby:
        """Join the lobby with this secret, creating it if needed. Needs a bearer token.

        Discord: https://docs.discord.com/developers/resources/lobby#create-or-join-lobby
        """
        return await self.request(CREATE_OR_JOIN_LOBBY.compile(), Lobby, body=params)

    async def get(self, lobby_id: int) -> Lobby:
        """Get a lobby.

        Discord: https://docs.discord.com/developers/resources/lobby#get-lobby
        """
        return await self.request(GET_LOBBY.compile(lobby_id=lobby_id), Lobby)

    async def edit(self, lobby_id: int, params: EditLobbyParams) -> Lobby:
        """Change a lobby's metadata, members or idle timeout.

        Discord: https://docs.discord.com/developers/resources/lobby#modify-lobby
        """
        return await self.request(MODIFY_LOBBY.compile(lobby_id=lobby_id), Lobby, body=params)

    async def delete(self, lobby_id: int) -> None:
        """Delete a lobby; safe to call again.

        Discord: https://docs.discord.com/developers/resources/lobby#delete-lobby
        """
        await self.request_empty(DELETE_LOBBY.compile(lobby_id=lobby_id))

    async def add_member(
        self, lobby_id: int, user_id: int, params: AddLobbyMemberParams | None = None
    ) -> LobbyMember:
        """Add a user to a lobby, or update them if they are in it.

        Discord: https://docs.discord.com/developers/resources/lobby#add-a-member-to-a-lobby
        """
        return await self.request(
            ADD_A_MEMBER_TO_A_LOBBY.compile(lobby_id=lobby_id, user_id=user_id),
            LobbyMember,
            body=params or AddLobbyMemberParams(),
        )

    async def bulk_edit_members(
        self, lobby_id: int, members: Sequence[BulkLobbyMemberParams]
    ) -> list[LobbyMember]:
        """Add, update or remove 1 to 25 members; returns those added or updated.

        Users who fail checks or are in too many lobbies are dropped without an error.

        Discord: https://docs.discord.com/developers/resources/lobby#bulk-update-lobby-members
        """
        return await self.request(
            BULK_UPDATE_LOBBY_MEMBERS.compile(lobby_id=lobby_id), list[LobbyMember], body=list(members)
        )

    async def remove_member(self, lobby_id: int, user_id: int) -> None:
        """Remove a user from a lobby; safe when they already left.

        Discord: https://docs.discord.com/developers/resources/lobby#remove-a-member-from-a-lobby
        """
        await self.request_empty(REMOVE_A_MEMBER_FROM_A_LOBBY.compile(lobby_id=lobby_id, user_id=user_id))

    async def leave(self, lobby_id: int) -> None:
        """Leave a lobby as the current user. Needs a bearer token.

        Discord: https://docs.discord.com/developers/resources/lobby#leave-lobby
        """
        await self.request_empty(LEAVE_LOBBY.compile(lobby_id=lobby_id))

    async def link_channel(self, lobby_id: int, channel_id: int) -> Lobby:
        """Link a text channel to a lobby. Needs a bearer token of a member who can link lobbies.

        Discord: https://docs.discord.com/developers/resources/lobby#link-channel-to-lobby
        """
        return await self.request(
            LINK_CHANNEL_TO_LOBBY.compile(lobby_id=lobby_id),
            Lobby,
            body=LinkLobbyChannelParams(channel_id=Snowflake(channel_id)),
        )

    async def unlink_channel(self, lobby_id: int) -> Lobby:
        """Unlink the lobby's channel. Needs a bearer token of a member who can link lobbies.

        Discord: https://docs.discord.com/developers/resources/lobby#unlink-channel-from-lobby
        """
        return await self.request(
            UNLINK_CHANNEL_FROM_LOBBY.compile(lobby_id=lobby_id), Lobby, body=LinkLobbyChannelParams()
        )

    async def send_message(self, lobby_id: int, params: SendLobbyMessageParams) -> LobbyMessage:
        """Send a message to a lobby the user is in; also posted to a linked channel.

        Needs a bearer token.

        Discord: https://docs.discord.com/developers/resources/lobby#send-lobby-message
        """
        return await self.request(SEND_LOBBY_MESSAGE.compile(lobby_id=lobby_id), LobbyMessage, body=params)

    async def list_messages(
        self, lobby_id: int, params: ListLobbyMessagesParams | None = None
    ) -> list[LobbyMessage]:
        """List a lobby's recent messages. Needs a bearer token of a member.

        Discord: https://docs.discord.com/developers/resources/lobby#get-lobby-messages
        """
        return await self.request(
            GET_LOBBY_MESSAGES.compile(lobby_id=lobby_id),
            list[LobbyMessage],
            query=query_of(params) if params is not None else None,
        )

    async def edit_message_moderation(
        self, lobby_id: int, message_id: int, metadata: Mapping[str, str]
    ) -> None:
        """Record a moderation decision on a message: up to 5 free-form keys. Needs a bot token.

        Discord: https://docs.discord.com/developers/resources/lobby#update-lobby-message-moderation-metadata
        """
        await self.request_empty(
            UPDATE_LOBBY_MESSAGE_MODERATION_METADATA.compile(lobby_id=lobby_id, message_id=message_id),
            body=dict(metadata),
        )

    async def create_my_invite(self, lobby_id: int) -> LobbyInvite:
        """Create a one-hour, single-use invite to the linked channel for the current user.

        Needs a bearer token.

        Discord: https://docs.discord.com/developers/resources/lobby#create-lobby-channel-invite-for-self
        """
        return await self.request(
            CREATE_LOBBY_CHANNEL_INVITE_FOR_SELF.compile(lobby_id=lobby_id), LobbyInvite
        )

    async def create_invite(self, lobby_id: int, user_id: int) -> LobbyInvite:
        """Create a one-hour, single-use invite to the linked channel for a user. Needs a bot token.

        Discord: https://docs.discord.com/developers/resources/lobby#create-lobby-channel-invite-for-user
        """
        return await self.request(
            CREATE_LOBBY_CHANNEL_INVITE_FOR_USER.compile(lobby_id=lobby_id, user_id=user_id), LobbyInvite
        )
