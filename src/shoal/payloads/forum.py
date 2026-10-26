"""Starting a post in a forum or media channel: a thread and its first message, in one request.

Discord: https://docs.discord.com/developers/resources/channel#start-thread-in-forum-or-media-channel
"""

from msgspec import UNSET, UnsetType

from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload
from shoal.payloads.channel import Channel
from shoal.payloads.components import MessageComponent
from shoal.payloads.message import AllowedMentions, AttachmentRequest, Embed, Message, MessageFlags


class ForumThreadMessageParams(Payload):
    """The first message of a forum or media post.

    It needs content, embeds, stickers, components or files.

    Discord: https://docs.discord.com/developers/resources/channel#start-thread-in-forum-or-media-channel-forum-and-media-thread-message-params-object
    """

    content: str | UnsetType = UNSET
    """Up to 2000 characters."""
    embeds: list[Embed] | UnsetType = UNSET
    """Up to 10."""
    allowed_mentions: AllowedMentions | UnsetType = UNSET
    components: list[MessageComponent] | UnsetType = UNSET
    sticker_ids: list[Snowflake] | UnsetType = UNSET
    """Up to 3 of the guild's stickers."""
    attachments: list[AttachmentRequest] | UnsetType = UNSET
    """Filled in from the files passed when left unset."""
    flags: MessageFlags | UnsetType = UNSET
    """Only `suppress_embeds` and `suppress_notifications` can be set."""


class StartThreadInForumParams(Payload):
    """JSON body of Start Thread in Forum or Media Channel.

    Discord: https://docs.discord.com/developers/resources/channel#start-thread-in-forum-or-media-channel-jsonform-params
    """

    name: str
    """1 to 100 characters."""
    auto_archive_duration: int | UnsetType = UNSET
    """Minutes: 60, 1440, 4320 or 10080."""
    rate_limit_per_user: int | UnsetType | None = UNSET
    message: ForumThreadMessageParams
    applied_tags: list[Snowflake] | UnsetType = UNSET


class ForumThread(Channel):
    """The thread Start Thread in Forum or Media Channel creates, with its first message.

    Discord: https://docs.discord.com/developers/resources/channel#start-thread-in-forum-or-media-channel
    """

    message: Message
