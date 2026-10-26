"""Polls in messages.

Discord: https://docs.discord.com/developers/resources/poll
"""

from datetime import datetime

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload
from shoal.payloads.emoji import PartialEmoji
from shoal.payloads.user import User


class PollLayoutType(DiscordIntEnum):
    """How a poll is laid out. There is one layout so far.

    Discord: https://docs.discord.com/developers/resources/poll#layout-type
    """

    DEFAULT = 1


class PollMedia(Payload):
    """The text, and for answers an optional emoji, of a poll's question or answer.

    The question takes up to 300 characters and only `text`; an answer takes up to 55. When
    sending an emoji, give only its `id` (custom) or `name` (unicode).

    Discord: https://docs.discord.com/developers/resources/poll#poll-media-object
    """

    text: str | UnsetType = UNSET
    emoji: PartialEmoji | UnsetType = UNSET


class PollAnswer(Payload):
    """One answer of a poll.

    Discord: https://docs.discord.com/developers/resources/poll#poll-answer-object
    """

    answer_id: int | UnsetType = UNSET
    """Set by Discord; leave it out when creating a poll."""
    poll_media: PollMedia


class PollAnswerCount(Payload):
    """The votes for one answer.

    Discord: https://docs.discord.com/developers/resources/poll#poll-results-object-poll-answer-count-object-structure
    """

    id: int
    """The `answer_id`."""
    count: int
    me_voted: bool


class PollResults(Payload):
    """The votes so far. An answer missing from `answer_counts` has none.

    Counts can be slightly off while the poll runs; they are exact once `is_finalized`.

    Discord: https://docs.discord.com/developers/resources/poll#poll-results-object
    """

    is_finalized: bool
    answer_counts: list[PollAnswerCount]


class Poll(Payload):
    """A poll on a message.

    Discord: https://docs.discord.com/developers/resources/poll#poll-object
    """

    question: PollMedia
    answers: list[PollAnswer]
    expiry: datetime | None
    """Every poll has one today; `None` is reserved for polls that never end."""
    allow_multiselect: bool
    layout_type: PollLayoutType
    results: PollResults | UnsetType = UNSET
    """Missing when Discord did not fetch them; that means unknown, not zero."""


class PollCreateRequest(Payload):
    """A poll to send with a message. It cannot be edited afterwards.

    Discord: https://docs.discord.com/developers/resources/poll#poll-create-request-object
    """

    question: PollMedia
    answers: list[PollAnswer]
    """Up to 10."""
    duration: int | UnsetType = UNSET
    """Hours, up to 32 days; Discord's default is 24."""
    allow_multiselect: bool | UnsetType = UNSET
    layout_type: PollLayoutType | UnsetType = UNSET


class GetAnswerVotersParams(Payload):
    """Query of Get Answer Voters.

    Discord: https://docs.discord.com/developers/resources/poll#get-answer-voters-query-string-params
    """

    after: Snowflake | UnsetType = UNSET
    """A user ID."""
    limit: int | UnsetType = UNSET
    """1 to 100; Discord's default is 25."""


class AnswerVoters(Payload):
    """The response of Get Answer Voters.

    Discord: https://docs.discord.com/developers/resources/poll#get-answer-voters-response-body
    """

    users: list[User]
