"""Models: users, members, guilds, roles, channels, threads, messages and emojis.

Each model wraps a payload and a `State` (the REST client and the cache), so attributes read the
payload, lookups such as `guild.get_member` read the cache synchronously, and methods such as
`message.reply` call Discord. `shoal.Client` builds them for its events; they can also be built by
hand from REST answers for a dashboard or worker.

Discord: https://docs.discord.com/developers/reference
"""

from shoal.models.activity import Competing, CustomActivity, Game, Listening, Streaming, Watching
from shoal.models.asset import Asset, ImageFormat
from shoal.models.base import MISSING, Hashable, MissingType, Object
from shoal.models.channel import (
    AnyGuildChannel,
    CategoryChannel,
    DMChannel,
    ForumChannel,
    GroupChannel,
    GuildChannel,
    MediaChannel,
    MessageableChannel,
    PartialMessageable,
    StageChannel,
    TextChannel,
    ThreadWithMessage,
    VoiceChannel,
    channel_from_payload,
)
from shoal.models.embed import Embed
from shoal.models.emoji import Emoji
from shoal.models.guild import Guild
from shoal.models.member import Member
from shoal.models.message import Message, PartialMessage, Reaction
from shoal.models.messageable import Messageable, Typing
from shoal.models.permissions import channel_permissions, guild_permissions, thread_permissions
from shoal.models.role import Role
from shoal.models.state import ComponentView, State, ViewRegistry
from shoal.models.thread import Thread
from shoal.models.user import BaseUser, ClientUser, User

__all__ = [
    "MISSING",
    "AnyGuildChannel",
    "Asset",
    "BaseUser",
    "CategoryChannel",
    "ClientUser",
    "Competing",
    "ComponentView",
    "CustomActivity",
    "DMChannel",
    "Embed",
    "Emoji",
    "ForumChannel",
    "Game",
    "GroupChannel",
    "Guild",
    "GuildChannel",
    "Hashable",
    "ImageFormat",
    "Listening",
    "MediaChannel",
    "Member",
    "Message",
    "Messageable",
    "MessageableChannel",
    "MissingType",
    "Object",
    "PartialMessage",
    "PartialMessageable",
    "Reaction",
    "Role",
    "StageChannel",
    "State",
    "Streaming",
    "TextChannel",
    "Thread",
    "ThreadWithMessage",
    "Typing",
    "User",
    "ViewRegistry",
    "VoiceChannel",
    "Watching",
    "channel_from_payload",
    "channel_permissions",
    "guild_permissions",
    "thread_permissions",
]
