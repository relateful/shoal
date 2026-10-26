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
from shoal.rest.files import File
from tests.support.models import ROW_VIEW, StaticView


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


def test_left_out_edit_keywords_are_kept_and_none_clears() -> None:
    assert json(edit().message_params()) == {}
    cleared = edit(content=None, embed=None, view=None, allowed_mentions=None)
    assert json(cleared.message_params()) == {
        "content": None,
        "embeds": None,
        "allowed_mentions": None,
        "components": None,
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
