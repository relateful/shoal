import msgspec
import pytest

from shoal.core.codec import encode_json
from shoal.models.base import MISSING
from shoal.models.embed import Embed
from shoal.models.sending import edit, outgoing
from shoal.payloads import (
    AllowedMentions,
    MessageFlags,
    MessageReference,
    TextDisplay,
)
from shoal.payloads import Embed as EmbedPayload
from shoal.payloads.poll import PollCreateRequest, PollMedia
from shoal.rest.files import File, VoiceMessage
from tests.support.calls import call_unchecked
from tests.support.models import ROW, ROW_VIEW, StaticView


def json(value: object) -> object:
    return msgspec.json.decode(encode_json(value))


def test_send_keywords_become_create_message() -> None:
    message = outgoing(
        42,
        tts=True,
        embed=Embed(title="t"),
        file=File("a.txt", b"a"),
        allowed_mentions=AllowedMentions.none(),
        view=ROW_VIEW,
        suppress_embeds=True,
        silent=True,
    )
    params = message.message_params(reference=MessageReference(message_id=msgspec.UNSET), sticker_ids=[9])
    assert json(params) == {
        "content": "42",
        "tts": True,
        "embeds": [{"title": "t"}],
        "allowed_mentions": {"parse": []},
        "message_reference": {},
        "components": [
            {"type": 1, "components": [{"type": 2, "style": 1, "custom_id": "ok", "label": "OK"}]}
        ],
        "sticker_ids": ["9"],
        "flags": int(MessageFlags(suppress_embeds=True, suppress_notifications=True)),
    }
    assert [file.filename for file in message.files] == ["a.txt"]


def test_nothing_given_sends_nothing() -> None:
    assert json(outgoing().message_params()) == {}
    assert json(outgoing().interaction_message()) == {}
    assert json(outgoing().followup_params()) == {}


def test_components_v2_set_their_flag() -> None:
    message = outgoing(view=StaticView(TextDisplay(content="hi")))
    assert isinstance(message.flags, MessageFlags)
    assert message.flags.is_components_v2


def test_components_v2_replace_content_embeds_polls_and_stickers() -> None:
    v2 = StaticView(TextDisplay(content="hi"))
    with pytest.raises(TypeError, match="Components V2"):
        outgoing("hi", view=v2)
    with pytest.raises(TypeError, match="Components V2"):
        outgoing(embed=Embed(title="t"), view=v2)
    with pytest.raises(TypeError, match="Components V2"):
        outgoing(embeds=[], view=v2)
    with pytest.raises(TypeError, match="stickers"):
        outgoing(view=v2).message_params(sticker_ids=[1])
    with pytest.raises(TypeError, match="Components V2"):
        edit(view=v2, content="hi")
    with pytest.raises(TypeError, match="Components V2"):
        edit(view=v2, embed=Embed(title="t"))
    # Clearing them is what a message turning into Components V2 needs.
    assert json(edit(view=v2, content=None).message_params()) == {
        "content": None,
        "components": [{"type": 10, "content": "hi"}],
        "flags": int(MessageFlags(is_components_v2=True)),
    }
    # A message already in Components V2 keeps its flag; text cannot be added back.
    with pytest.raises(TypeError, match="Components V2"):
        edit(view=v2, content="hi", flags=MessageFlags(is_components_v2=True))
    # Action rows only: content is fine.
    assert json(outgoing("hi", view=ROW_VIEW).message_params()) == {
        "content": "hi",
        "components": [json(ROW)],
    }


def test_ephemeral_is_a_flag_for_interaction_responses() -> None:
    data = json(outgoing("hi", ephemeral=True, embeds=[EmbedPayload(title="x")]).interaction_message())
    assert data == {"content": "hi", "embeds": [{"title": "x"}], "flags": int(MessageFlags(ephemeral=True))}


def test_embed_and_embeds_or_file_and_files_cannot_be_combined() -> None:
    with pytest.raises(TypeError, match="embed and embeds"):
        outgoing(embed=Embed(), embeds=[Embed()])
    with pytest.raises(TypeError, match="file and files"):
        outgoing(file=File("a", b""), files=[File("b", b"")])
    with pytest.raises(TypeError, match="embed and embeds"):
        edit(embed=Embed(), embeds=[])


def test_a_components_v2_message_cannot_drop_its_layout() -> None:
    with pytest.raises(TypeError, match="cannot drop it"):
        edit(view=None, flags=MessageFlags(is_components_v2=True))


def test_left_out_edit_keywords_are_kept_and_none_clears() -> None:
    assert json(edit().message_params()) == {}
    cleared = edit(content=None, embed=None, view=None, allowed_mentions=None)
    assert json(cleared.message_params()) == {
        "content": None,
        "embeds": [],
        "allowed_mentions": None,
        "components": [],
    }
    assert json(edit(content=MISSING, embeds=[Embed(title="t")]).webhook_params()) == {
        "embeds": [{"title": "t"}]
    }


def test_edits_repeat_the_current_flags() -> None:
    current = MessageFlags(suppress_notifications=True)
    unsuppressed = edit(suppress=False, flags=current | MessageFlags(suppress_embeds=True))
    assert unsuppressed.flags == current
    assert edit(view=StaticView(TextDisplay(content="v2")), flags=current).flags == current.with_flags(
        is_components_v2=True
    )
    assert edit(view=ROW_VIEW, flags=current).flags is msgspec.UNSET


def test_an_update_response_cannot_send_null_so_clearing_sends_empty() -> None:
    assert json(edit(content=None, embed=None, view=None).interaction_message()) == {
        "content": "",
        "embeds": [],
        "components": [],
    }
    assert json(edit(content="x").interaction_message()) == {"content": "x"}


def test_new_files_ride_along_with_an_edit() -> None:
    changes = edit(attachments=[File("b.txt", b"b")])
    assert [file.filename for file in changes.files] == ["b.txt"]
    assert changes.view is None


def test_a_voice_message_is_sent_alone_with_its_flag() -> None:
    voice = VoiceMessage(b"ogg", 1.0, b"\x80")
    message = outgoing(voice_message=voice, silent=True)
    assert message.flags == MessageFlags(is_voice_message=True, suppress_notifications=True)
    assert [file.duration for file in message.files] == [1.0]
    extras: list[dict[str, object]] = [
        {"content": "hi"},
        {"embed": Embed()},
        {"embeds": []},
        {"file": File("a.txt", b"a")},
        {"files": []},
        {"view": ROW_VIEW},
        {"poll": PollCreateRequest(question=PollMedia(text="?"), answers=[])},
        {"tts": True},
        {"suppress_embeds": True},
    ]
    for extra in extras:
        with pytest.raises(TypeError, match="single audio attachment"):
            call_unchecked(outgoing, voice_message=voice, **extra)
    with pytest.raises(TypeError, match="single audio attachment"):
        message.message_params(sticker_ids=[1])
