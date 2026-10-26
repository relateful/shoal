"""Endpoints for messages, reactions, pins and polls.

Discord: https://docs.discord.com/developers/resources/message
"""

from collections.abc import Sequence

from shoal.core.snowflake import Snowflake
from shoal.payloads.emoji import Emoji, PartialEmoji
from shoal.payloads.message import (
    BulkDeleteMessagesParams,
    ChannelPins,
    CreateMessageParams,
    EditMessageParams,
    GetChannelMessagesParams,
    GetChannelPinsParams,
    GetReactionsParams,
    Message,
)
from shoal.payloads.poll import AnswerVoters, GetAnswerVotersParams
from shoal.payloads.user import User
from shoal.rest.endpoints import (
    BULK_DELETE_MESSAGES,
    CREATE_MESSAGE,
    CREATE_REACTION,
    CROSSPOST_MESSAGE,
    DELETE_ALL_REACTIONS,
    DELETE_ALL_REACTIONS_FOR_EMOJI,
    DELETE_MESSAGE,
    DELETE_OWN_REACTION,
    DELETE_USER_REACTION,
    EDIT_MESSAGE,
    END_POLL,
    GET_ANSWER_VOTERS,
    GET_CHANNEL_MESSAGE,
    GET_CHANNEL_MESSAGES,
    GET_CHANNEL_PINS,
    GET_REACTIONS,
    PIN_MESSAGE,
    UNPIN_MESSAGE,
)
from shoal.rest.files import File
from shoal.rest.requester import Requester, query_of, with_attachments

type ReactionEmoji = str | Emoji | PartialEmoji
"""An emoji to react with: a unicode emoji, `name:id` for a custom one, or an emoji object."""


def reaction_emoji(emoji: ReactionEmoji) -> str:
    """The emoji as the reaction endpoints take it: the unicode emoji, or `name:id`.

    Raises:
        ValueError: The emoji object has no name, as reactions to a deleted custom emoji do.

    Discord: https://docs.discord.com/developers/resources/message#create-reaction
    """
    if isinstance(emoji, str):
        return emoji
    name = emoji.name if isinstance(emoji.name, str) else None
    emoji_id = emoji.id if isinstance(emoji.id, int) else None
    if name is None:
        msg = "a reaction emoji needs its name: the unicode emoji, or the custom emoji's name"
        raise ValueError(msg)
    return name if emoji_id is None else f"{name}:{emoji_id}"


class MessageEndpoints(Requester):
    """Endpoints for messages, reactions, pins and polls; part of `RestClient`."""

    __slots__ = ()

    async def get_channel_messages(
        self, channel_id: int, params: GetChannelMessagesParams | None = None
    ) -> list[Message]:
        """List a channel's messages, newest first.

        Needs View Channel (and Connect in voice channels); without Read Message History the list
        is empty.

        Discord: https://docs.discord.com/developers/resources/message#get-channel-messages
        """
        return await self.request(
            GET_CHANNEL_MESSAGES.compile(channel_id=channel_id),
            list[Message],
            query=query_of(params) if params is not None else None,
        )

    async def get_channel_message(self, channel_id: int, message_id: int) -> Message:
        """Get one message.

        Discord: https://docs.discord.com/developers/resources/message#get-channel-message
        """
        return await self.request(
            GET_CHANNEL_MESSAGE.compile(channel_id=channel_id, message_id=message_id), Message
        )

    async def create_message(
        self, channel_id: int, params: CreateMessageParams, *, files: Sequence[File] = ()
    ) -> Message:
        """Send a message, with any files attached.

        Needs Send Messages (and Send TTS Messages for `tts`, Read Message History for a reply). A
        request may be at most 25 MiB.

        Discord: https://docs.discord.com/developers/resources/message#create-message
        """
        body, named = with_attachments(params, files)
        return await self.request(
            CREATE_MESSAGE.compile(channel_id=channel_id), Message, body=body, files=named
        )

    async def crosspost_message(self, channel_id: int, message_id: int) -> Message:
        """Publish a message in an announcement channel to the channels following it.

        Needs Send Messages for the bot's own messages, and Manage Messages for others'.

        Discord: https://docs.discord.com/developers/resources/message#crosspost-message
        """
        return await self.request(
            CROSSPOST_MESSAGE.compile(channel_id=channel_id, message_id=message_id), Message
        )

    async def create_reaction(self, channel_id: int, message_id: int, emoji: ReactionEmoji) -> None:
        """React to a message. Needs Read Message History, and Add Reactions for a new emoji.

        Discord: https://docs.discord.com/developers/resources/message#create-reaction
        """
        await self.request_empty(
            CREATE_REACTION.compile(
                channel_id=channel_id, message_id=message_id, emoji_id=reaction_emoji(emoji)
            )
        )

    async def delete_own_reaction(self, channel_id: int, message_id: int, emoji: ReactionEmoji) -> None:
        """Remove the current user's reaction.

        Discord: https://docs.discord.com/developers/resources/message#delete-own-reaction
        """
        await self.request_empty(
            DELETE_OWN_REACTION.compile(
                channel_id=channel_id, message_id=message_id, emoji_id=reaction_emoji(emoji)
            )
        )

    async def delete_user_reaction(
        self, channel_id: int, message_id: int, emoji: ReactionEmoji, user_id: int
    ) -> None:
        """Remove another user's reaction. Needs Manage Messages.

        Discord: https://docs.discord.com/developers/resources/message#delete-user-reaction
        """
        await self.request_empty(
            DELETE_USER_REACTION.compile(
                channel_id=channel_id, message_id=message_id, emoji_id=reaction_emoji(emoji), user_id=user_id
            )
        )

    async def get_reactions(
        self,
        channel_id: int,
        message_id: int,
        emoji: ReactionEmoji,
        params: GetReactionsParams | None = None,
    ) -> list[User]:
        """List the users who reacted with an emoji.

        Discord: https://docs.discord.com/developers/resources/message#get-reactions
        """
        return await self.request(
            GET_REACTIONS.compile(
                channel_id=channel_id, message_id=message_id, emoji_id=reaction_emoji(emoji)
            ),
            list[User],
            query=query_of(params) if params is not None else None,
        )

    async def delete_all_reactions(self, channel_id: int, message_id: int) -> None:
        """Remove every reaction from a message. Needs Manage Messages.

        Discord: https://docs.discord.com/developers/resources/message#delete-all-reactions
        """
        await self.request_empty(DELETE_ALL_REACTIONS.compile(channel_id=channel_id, message_id=message_id))

    async def delete_all_reactions_for_emoji(
        self, channel_id: int, message_id: int, emoji: ReactionEmoji
    ) -> None:
        """Remove every reaction with one emoji from a message. Needs Manage Messages.

        Discord: https://docs.discord.com/developers/resources/message#delete-all-reactions-for-emoji
        """
        await self.request_empty(
            DELETE_ALL_REACTIONS_FOR_EMOJI.compile(
                channel_id=channel_id, message_id=message_id, emoji_id=reaction_emoji(emoji)
            )
        )

    async def edit_message(
        self, channel_id: int, message_id: int, params: EditMessageParams, *, files: Sequence[File] = ()
    ) -> Message:
        """Edit a message; files passed are added to it.

        Discord: https://docs.discord.com/developers/resources/message#edit-message
        """
        body, named = with_attachments(params, files, edit=True)
        return await self.request(
            EDIT_MESSAGE.compile(channel_id=channel_id, message_id=message_id),
            Message,
            body=body,
            files=named,
        )

    async def delete_message(self, channel_id: int, message_id: int, *, reason: str | None = None) -> None:
        """Delete a message. Needs Manage Messages for other users' messages in a guild.

        Discord: https://docs.discord.com/developers/resources/message#delete-message
        """
        await self.request_empty(
            DELETE_MESSAGE.compile(channel_id=channel_id, message_id=message_id), reason=reason
        )

    async def bulk_delete_messages(
        self, channel_id: int, message_ids: Sequence[int], *, reason: str | None = None
    ) -> None:
        """Delete 2 to 100 messages at once, none older than two weeks. Needs Manage Messages.

        Discord: https://docs.discord.com/developers/resources/message#bulk-delete-messages
        """
        await self.request_empty(
            BULK_DELETE_MESSAGES.compile(channel_id=channel_id),
            body=BulkDeleteMessagesParams(messages=[Snowflake(message_id) for message_id in message_ids]),
            reason=reason,
        )

    async def get_channel_pins(
        self, channel_id: int, params: GetChannelPinsParams | None = None
    ) -> ChannelPins:
        """List a channel's pins, up to 50 at a time, most recently pinned first.

        Discord: https://docs.discord.com/developers/resources/message#get-channel-pins
        """
        return await self.request(
            GET_CHANNEL_PINS.compile(channel_id=channel_id),
            ChannelPins,
            query=query_of(params) if params is not None else None,
        )

    async def pin_message(self, channel_id: int, message_id: int, *, reason: str | None = None) -> None:
        """Pin a message. Needs Pin Messages.

        Discord: https://docs.discord.com/developers/resources/message#pin-message
        """
        await self.request_empty(
            PIN_MESSAGE.compile(channel_id=channel_id, message_id=message_id), reason=reason
        )

    async def unpin_message(self, channel_id: int, message_id: int, *, reason: str | None = None) -> None:
        """Unpin a message. Needs Pin Messages.

        Discord: https://docs.discord.com/developers/resources/message#unpin-message
        """
        await self.request_empty(
            UNPIN_MESSAGE.compile(channel_id=channel_id, message_id=message_id), reason=reason
        )

    async def get_answer_voters(
        self,
        channel_id: int,
        message_id: int,
        answer_id: int,
        params: GetAnswerVotersParams | None = None,
    ) -> list[User]:
        """List the users who voted for one answer of a poll.

        Discord: https://docs.discord.com/developers/resources/poll#get-answer-voters
        """
        response = await self.request(
            GET_ANSWER_VOTERS.compile(channel_id=channel_id, message_id=message_id, answer_id=answer_id),
            AnswerVoters,
            query=query_of(params) if params is not None else None,
        )
        return response.users

    async def end_poll(self, channel_id: int, message_id: int) -> Message:
        """End one of the bot's polls now.

        Discord: https://docs.discord.com/developers/resources/poll#end-poll
        """
        return await self.request(END_POLL.compile(channel_id=channel_id, message_id=message_id), Message)
