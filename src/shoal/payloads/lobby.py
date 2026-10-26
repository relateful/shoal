"""Lobbies: groups of players that chat through the Social SDK, managed from a game's server.

Discord: https://docs.discord.com/developers/resources/lobby
"""

from msgspec import UNSET, UnsetType

from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload
from shoal.payloads.channel import Channel
from shoal.payloads.message import MessageFlags, MessageType
from shoal.payloads.user import User


class LobbyMemberFlags(BaseFlags):
    """Flags of a lobby member.

    Discord: https://docs.discord.com/developers/resources/lobby#lobby-member-object-lobby-member-flags
    """

    __slots__ = ()

    can_link_lobby = flag(0)
    """The member can link a text channel to the lobby."""


class LobbyMember(Payload):
    """A member of a lobby.

    Discord: https://docs.discord.com/developers/resources/lobby#lobby-member-object
    """

    id: Snowflake
    """The user's ID."""
    metadata: dict[str, str] | UnsetType | None = UNSET
    """Up to 1000 characters in total."""
    flags: LobbyMemberFlags | UnsetType = UNSET
    additional_name: str | UnsetType = UNSET
    """A second display name, such as an in-game character name; only settable over HTTP."""


class Lobby(Payload):
    """A lobby.

    Discord: https://docs.discord.com/developers/resources/lobby#lobby-object
    """

    id: Snowflake
    application_id: Snowflake
    metadata: dict[str, str] | None
    """Up to 1000 characters in total."""
    members: list[LobbyMember]
    linked_channel: Channel | UnsetType = UNSET


class LobbyMemberParams(Payload):
    """A member in Create Lobby or Modify Lobby.

    Discord: https://docs.discord.com/developers/resources/lobby#lobby-member-json-params
    """

    id: Snowflake
    metadata: dict[str, str] | UnsetType | None = UNSET
    flags: LobbyMemberFlags | UnsetType = UNSET
    additional_name: str | UnsetType | None = UNSET
    """1 to 80 characters; leave out to keep the current one, `None` to clear it."""


class BulkEditLobbyMemberParams(Payload):
    """One member to add, update or remove in Bulk Update Lobby Members.

    Discord: https://docs.discord.com/developers/resources/lobby#bulk-update-lobby-members
    """

    id: Snowflake
    metadata: dict[str, str] | UnsetType | None = UNSET
    flags: LobbyMemberFlags | UnsetType = UNSET
    additional_name: str | UnsetType | None = UNSET
    remove_member: bool | UnsetType = UNSET
    """Remove the user instead of adding or updating them."""


class CreateLobbyParams(Payload):
    """JSON body of Create Lobby.

    Discord: https://docs.discord.com/developers/resources/lobby#create-lobby
    """

    metadata: dict[str, str] | UnsetType | None = UNSET
    members: list[LobbyMemberParams] | UnsetType = UNSET
    """Up to 25."""
    idle_timeout_seconds: int | UnsetType = UNSET
    """5 to 604800 (7 days)."""


class CreateOrJoinLobbyParams(Payload):
    """JSON body of Create or Join Lobby.

    Discord: https://docs.discord.com/developers/resources/lobby#create-or-join-lobby
    """

    REDACTED_FIELDS = frozenset({"secret"})

    secret: str
    """Identifies the lobby; up to 250 characters."""
    idle_timeout_seconds: int | UnsetType = UNSET
    lobby_metadata: dict[str, str] | UnsetType | None = UNSET
    """Replaces the lobby's metadata."""
    member_metadata: dict[str, str] | UnsetType | None = UNSET
    """Set on the calling user's membership."""


class EditLobbyParams(Payload):
    """JSON body of Modify Lobby.

    Discord: https://docs.discord.com/developers/resources/lobby#modify-lobby
    """

    metadata: dict[str, str] | UnsetType | None = UNSET
    """Replaces the existing metadata."""
    members: list[LobbyMemberParams] | UnsetType = UNSET
    """Up to 25; replaces the members, removing anyone not listed."""
    idle_timeout_seconds: int | UnsetType = UNSET


class AddLobbyMemberParams(Payload):
    """JSON body of Add a Member to a Lobby, which also updates an existing member.

    Discord: https://docs.discord.com/developers/resources/lobby#add-a-member-to-a-lobby
    """

    metadata: dict[str, str] | UnsetType | None = UNSET
    flags: LobbyMemberFlags | UnsetType = UNSET
    additional_name: str | UnsetType | None = UNSET


class LinkLobbyChannelParams(Payload):
    """JSON body of Link Channel to Lobby.

    Discord: https://docs.discord.com/developers/resources/lobby#link-channel-to-lobby
    """

    channel_id: Snowflake | UnsetType = UNSET
    """Leaving it out unlinks any linked channel."""


class SendLobbyMessageParams(Payload):
    """JSON body of Send Lobby Message.

    Discord: https://docs.discord.com/developers/resources/lobby#send-lobby-message
    """

    content: str
    """Must not be empty."""
    metadata: dict[str, str] | UnsetType | None = UNSET
    """Delivered to Social SDK clients; not kept on a linked channel's message."""
    flags: MessageFlags | UnsetType = UNSET
    """Only flags the Social SDK can create."""


class LobbyMessageMember(Payload):
    """The author's lobby display name when they sent a message.

    Discord: https://docs.discord.com/developers/resources/lobby#lobby-message-object
    """

    additional_name: str


class LobbyMessage(Payload):
    """A message sent in a lobby.

    Discord: https://docs.discord.com/developers/resources/lobby#lobby-message-object
    """

    id: Snowflake
    type: MessageType
    content: str
    lobby_id: Snowflake
    channel_id: Snowflake
    """The same as `lobby_id`."""
    author: User
    lobby_member: LobbyMessageMember | UnsetType = UNSET
    metadata: dict[str, str] | UnsetType | None = UNSET
    moderation_metadata: dict[str, str] | UnsetType | None = UNSET
    flags: MessageFlags
    application_id: Snowflake


class ListLobbyMessagesParams(Payload):
    """Query of Get Lobby Messages.

    Discord: https://docs.discord.com/developers/resources/lobby#get-lobby-messages
    """

    limit: int | UnsetType = UNSET
    """1 to 200; Discord's default is 50."""


class LobbyInvite(Payload):
    """A single-use invite to a lobby's linked channel; it expires after an hour.

    Discord: https://docs.discord.com/developers/resources/lobby#lobby-invite-object
    """

    code: str
