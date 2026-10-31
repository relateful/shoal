from datetime import UTC, datetime

import pytest

from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    AttachmentRequest,
    CreateMessageParams,
    EditMessageParams,
    Emoji,
    ListMessagesParams,
    ListPinsParams,
    ListReactionsParams,
    ListVotersParams,
    MessageFlags,
    PartialEmoji,
    PollAnswer,
    PollCreateRequest,
    PollMedia,
    ReactionType,
)
from shoal.rest.files import File
from shoal.rest.resources.message import reaction_emoji
from tests.support.json_payloads import MESSAGE, USER
from tests.support.multipart import FormPart
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

POLL: dict[str, object] = {
    "question": {"text": "Lunch?"},
    "answers": [
        {"answer_id": 1, "poll_media": {"text": "Pizza", "emoji": {"name": "\N{SLICE OF PIZZA}"}}},
        {"answer_id": 2, "poll_media": {"text": "Salad"}},
    ],
    "expiry": "2026-01-02T00:00:00+00:00",
    "allow_multiselect": False,
    "layout_type": 1,
    "results": {"is_finalized": False, "answer_counts": [{"id": 1, "count": 3, "me_voted": False}]},
}
RICH_MESSAGE: dict[str, object] = {
    **MESSAGE,
    "message_reference": {"type": 1, "message_id": "8", "channel_id": "3", "guild_id": "2"},
    "message_snapshots": [
        {"message": {"type": 0, "content": "forwarded", "timestamp": "2024-01-01T00:00:00+00:00"}}
    ],
    "interaction_metadata": {
        "id": "20",
        "type": 5,
        "user": USER,
        "authorizing_integration_owners": {"0": "2"},
        "triggering_interaction_metadata": {
            "id": "19",
            "type": 3,
            "user": USER,
            "authorizing_integration_owners": {"0": "2"},
            "interacted_message_id": "7",
        },
    },
    "poll": POLL,
    "call": {"participants": ["1"], "ended_timestamp": None},
}
"""A message using the newer fields: a forward, interaction metadata, a poll and a call."""
MESSAGES = "/channels/3/messages"
PIZZA = "%F0%9F%8D%95"
PNG = b"\x89PNG\r\n\x1a\n"

CASES = [
    EndpointCase(
        name="get messages",
        call=lambda client: client.messages.list(3, ListMessagesParams(before=Snowflake(9), limit=10)),
        method="GET",
        path=f"{MESSAGES}?before=9&limit=10",
        response=[RICH_MESSAGE],
    ),
    EndpointCase(
        name="get message",
        call=lambda client: client.messages.get(3, 9),
        method="GET",
        path=f"{MESSAGES}/9",
        response=MESSAGE,
    ),
    EndpointCase(
        name="create message",
        call=lambda client: client.messages.create(3, CreateMessageParams(content="hi")),
        method="POST",
        path=MESSAGES,
        body={"content": "hi"},
        response=MESSAGE,
    ),
    EndpointCase(
        name="create message with a poll",
        call=lambda client: client.messages.create(
            3,
            CreateMessageParams(
                poll=PollCreateRequest(
                    question=PollMedia(text="Lunch?"),
                    answers=[
                        PollAnswer(
                            poll_media=PollMedia(text="Pizza", emoji=PartialEmoji(name="\N{SLICE OF PIZZA}"))
                        )
                    ],
                    duration=4,
                )
            ),
        ),
        method="POST",
        path=MESSAGES,
        body={
            "poll": {
                "question": {"text": "Lunch?"},
                "answers": [{"poll_media": {"text": "Pizza", "emoji": {"name": "\N{SLICE OF PIZZA}"}}}],
                "duration": 4,
            }
        },
        response=RICH_MESSAGE,
    ),
    EndpointCase(
        name="create message with files",
        call=lambda client: client.messages.create(
            3,
            CreateMessageParams(content="the logs"),
            files=[
                File("crash.png", PNG, description="screenshot", content_type="image/png"),
                File("log.txt", b"boom"),
            ],
        ),
        method="POST",
        path=MESSAGES,
        body={
            "content": "the logs",
            "attachments": [
                {"id": 0, "filename": "crash.png", "description": "screenshot"},
                {"id": 1, "filename": "log.txt"},
            ],
        },
        files=(
            FormPart("files[0]", "crash.png", "image/png", PNG),
            FormPart("files[1]", "log.txt", "application/octet-stream", b"boom"),
        ),
        response=MESSAGE,
    ),
    EndpointCase(
        name="crosspost",
        call=lambda client: client.messages.crosspost(5, 9),
        method="POST",
        path="/channels/5/messages/9/crosspost",
        response=MESSAGE,
    ),
    EndpointCase(
        name="react with unicode",
        call=lambda client: client.reactions.add(3, 9, "\N{SLICE OF PIZZA}"),
        method="PUT",
        path=f"{MESSAGES}/9/reactions/{PIZZA}/@me",
    ),
    EndpointCase(
        name="react with a custom emoji",
        call=lambda client: client.reactions.add(3, 9, PartialEmoji(id=Snowflake(41), name="LUL")),
        method="PUT",
        path=f"{MESSAGES}/9/reactions/LUL%3A41/@me",
    ),
    EndpointCase(
        name="remove own reaction",
        call=lambda client: client.reactions.remove_mine(3, 9, "LUL:41"),
        method="DELETE",
        path=f"{MESSAGES}/9/reactions/LUL%3A41/@me",
    ),
    EndpointCase(
        name="remove a user's reaction",
        call=lambda client: client.reactions.remove(3, 9, "\N{SLICE OF PIZZA}", 1),
        method="DELETE",
        path=f"{MESSAGES}/9/reactions/{PIZZA}/1",
    ),
    EndpointCase(
        name="list reactions",
        call=lambda client: client.reactions.list(
            3, 9, "\N{SLICE OF PIZZA}", ListReactionsParams(type=ReactionType.BURST, limit=5)
        ),
        method="GET",
        path=f"{MESSAGES}/9/reactions/{PIZZA}?type=1&limit=5",
        response=[USER],
    ),
    EndpointCase(
        name="clear reactions",
        call=lambda client: client.reactions.clear(3, 9),
        method="DELETE",
        path=f"{MESSAGES}/9/reactions",
    ),
    EndpointCase(
        name="clear one emoji",
        call=lambda client: client.reactions.clear_emoji(3, 9, "\N{SLICE OF PIZZA}"),
        method="DELETE",
        path=f"{MESSAGES}/9/reactions/{PIZZA}",
    ),
    EndpointCase(
        name="edit message",
        call=lambda client: client.messages.edit(
            3, 9, EditMessageParams(content=None, flags=MessageFlags(suppress_embeds=True))
        ),
        method="PATCH",
        path=f"{MESSAGES}/9",
        body={"content": None, "flags": 4},
        response=MESSAGE,
    ),
    EndpointCase(
        name="edit message adding a file",
        call=lambda client: client.messages.edit(
            3, 9, EditMessageParams(content="v2"), files=[File("v2.txt", b"2")]
        ),
        method="PATCH",
        path=f"{MESSAGES}/9",
        body={"content": "v2"},
        files=(FormPart("files[0]", "v2.txt", "application/octet-stream", b"2"),),
        response=MESSAGE,
    ),
    EndpointCase(
        name="edit message replacing attachments",
        call=lambda client: client.messages.edit(
            3,
            9,
            EditMessageParams(
                attachments=[AttachmentRequest(id="12345"), AttachmentRequest(id=0, description="new")]
            ),
            files=[File("v2.txt", b"2")],
        ),
        method="PATCH",
        path=f"{MESSAGES}/9",
        body={"attachments": [{"id": "12345"}, {"id": 0, "description": "new"}]},
        files=(FormPart("files[0]", "v2.txt", "application/octet-stream", b"2"),),
        response=MESSAGE,
    ),
    EndpointCase(
        name="delete message",
        call=lambda client: client.messages.delete(3, 9),
        method="DELETE",
        path=f"{MESSAGES}/9",
    ),
    EndpointCase(
        name="bulk delete",
        call=lambda client: client.messages.bulk_delete(3, [9, 10], reason="raid"),
        method="POST",
        path=f"{MESSAGES}/bulk-delete",
        body={"messages": ["9", "10"]},
        reason="raid",
    ),
    EndpointCase(
        name="get pins",
        call=lambda client: client.messages.list_pins(
            3, ListPinsParams(before=datetime(2026, 1, 1, tzinfo=UTC), limit=50)
        ),
        method="GET",
        path=f"{MESSAGES}/pins?before=2026-01-01T00%3A00%3A00%2B00%3A00&limit=50",
        response={
            "items": [{"pinned_at": "2025-12-31T00:00:00+00:00", "message": MESSAGE}],
            "has_more": False,
        },
    ),
    EndpointCase(
        name="pin",
        call=lambda client: client.messages.pin(3, 9, reason="important"),
        method="PUT",
        path=f"{MESSAGES}/pins/9",
        reason="important",
    ),
    EndpointCase(
        name="unpin",
        call=lambda client: client.messages.unpin(3, 9),
        method="DELETE",
        path=f"{MESSAGES}/pins/9",
    ),
    EndpointCase(
        name="answer voters",
        call=lambda client: client.polls.list_voters(3, 9, 1, ListVotersParams(limit=100)),
        method="GET",
        path="/channels/3/polls/9/answers/1?limit=100",
        response={"users": [USER]},
        result=[USER],
    ),
    EndpointCase(
        name="end poll",
        call=lambda client: client.polls.end(3, 9),
        method="POST",
        path="/channels/3/polls/9/expire",
        response=RICH_MESSAGE,
    ),
]


@endpoint_cases(CASES)
async def test_message_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)


def test_reaction_emoji_takes_strings_and_emoji_objects() -> None:
    assert reaction_emoji("\N{SLICE OF PIZZA}") == "\N{SLICE OF PIZZA}"
    assert reaction_emoji(PartialEmoji(name="\N{SLICE OF PIZZA}")) == "\N{SLICE OF PIZZA}"
    assert reaction_emoji(Emoji(id=Snowflake(41), name="LUL")) == "LUL:41"
    with pytest.raises(ValueError, match="needs its name"):
        reaction_emoji(Emoji(id=Snowflake(41), name=None))
