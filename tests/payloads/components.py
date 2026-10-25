"""Components, checked against every message and modal example in Discord's components reference.

`fixtures/discord_component_examples.json` holds those examples verbatim from discord-api-docs, with
the JSONC comments and trailing commas removed. Each must decode into Shoal's types and encode back
to exactly the JSON Discord published.
"""

from pathlib import Path

import msgspec
import pytest

from shoal.core.codec import (
    JSONObject,
    PayloadDecodeError,
    convert,
    decode_json,
    decode_msgpack,
    encode_json,
    encode_msgpack,
)
from shoal.payloads import (
    ActionRow,
    Button,
    ButtonStyle,
    ChannelSelect,
    ChannelType,
    Container,
    CreateMessageParams,
    Label,
    Message,
    MessageComponent,
    MessageFlags,
    ModalComponent,
    PartialEmoji,
    Section,
    SeparatorSpacing,
    TextDisplay,
    TextInput,
    TextInputStyle,
    Thumbnail,
    UnfurledMediaItem,
    UnfurledMediaItemFlags,
    UnknownComponent,
    parse_components,
)
from shoal.payloads.components import Separator

EXAMPLES: dict[str, JSONObject] = msgspec.json.decode(
    (Path(__file__).parent / "fixtures" / "discord_component_examples.json").read_bytes(),
    type=dict[str, JSONObject],
)
MESSAGE_EXAMPLES = sorted(name for name in EXAMPLES if name.endswith("Message Example"))
MODAL_EXAMPLES = sorted(name for name in EXAMPLES if name.endswith("Modal Example"))


class _MessageBody(msgspec.Struct):
    flags: int | None = None
    components: list[MessageComponent] = msgspec.field(default_factory=list[MessageComponent])


class _ModalData(msgspec.Struct):
    custom_id: str
    title: str
    components: list[ModalComponent]


class _ModalResponse(msgspec.Struct):
    type: int
    data: _ModalData


def test_every_example_was_collected() -> None:
    assert len(MESSAGE_EXAMPLES) >= 10
    assert len(MODAL_EXAMPLES) >= 10


@pytest.mark.parametrize("name", MESSAGE_EXAMPLES)
def test_message_examples_round_trip_exactly(name: str) -> None:
    example = EXAMPLES[name]
    body = convert(example, _MessageBody)
    assert msgspec.json.decode(encode_json(body.components)) == example["components"]


@pytest.mark.parametrize("name", MODAL_EXAMPLES)
def test_modal_examples_round_trip_exactly(name: str) -> None:
    example = EXAMPLES[name]
    response = convert(example, _ModalResponse)
    assert response.type == 9
    assert msgspec.json.decode(encode_json(response.data.components)) == example["data"]["components"]


@pytest.mark.parametrize("name", MESSAGE_EXAMPLES)
def test_received_message_examples_parse_without_unknowns(name: str) -> None:
    components = convert(EXAMPLES[name]["components"], list[JSONObject])
    parsed = parse_components(components)
    assert not any(isinstance(component, UnknownComponent) for component in parsed)


def test_building_components_needs_no_type_numbers() -> None:
    row = ActionRow(
        components=[
            Button(style=ButtonStyle.PRIMARY, custom_id="yes", label="Accept"),
            Button(style=ButtonStyle.LINK, url="https://example.com", emoji=PartialEmoji(name="🔗")),
        ]
    )
    assert msgspec.json.decode(encode_json(row)) == {
        "type": 1,
        "components": [
            {"type": 2, "style": 1, "label": "Accept", "custom_id": "yes"},
            {"type": 2, "style": 5, "emoji": {"name": "🔗"}, "url": "https://example.com"},
        ],
    }


def test_components_v2_message_body() -> None:
    params = CreateMessageParams(
        flags=MessageFlags(is_components_v2=True),
        components=[
            Container(
                accent_color=0x1F6B5C,
                components=[
                    Section(
                        components=[TextDisplay(content="**Shoal**")],
                        accessory=Thumbnail(media=UnfurledMediaItem(url="attachment://fish.png")),
                    ),
                    Separator(spacing=SeparatorSpacing.LARGE),
                    ActionRow(
                        components=[ChannelSelect(custom_id="where", channel_types=[ChannelType.GUILD_TEXT])]
                    ),
                ],
            )
        ],
    )
    body = msgspec.json.decode(encode_json(params))
    assert body["flags"] == 1 << 15
    assert body["components"][0]["components"][2]["components"][0] == {
        "type": 8,
        "custom_id": "where",
        "channel_types": [0],
    }


def test_modal_label_wraps_a_text_input() -> None:
    label = Label(label="Name", component=TextInput(custom_id="name", style=TextInputStyle.SHORT))
    assert msgspec.json.decode(encode_json(label)) == {
        "type": 18,
        "label": "Name",
        "component": {"type": 4, "custom_id": "name", "style": 1},
    }


def test_unknown_types_survive_and_keep_their_data() -> None:
    raw: list[JSONObject] = [
        {"type": 10, "content": "known"},
        {"type": 99, "id": 7, "future": True},
        {"type": 17, "components": [{"type": 98}]},
    ]
    known, newer, holds_newer = parse_components(raw)
    assert known == TextDisplay(content="known")
    assert newer == UnknownComponent(type=99, id=7, data={"type": 99, "id": 7, "future": True})
    assert isinstance(holds_newer, UnknownComponent)
    assert holds_newer.type == 17


def test_entries_that_are_not_components_are_errors() -> None:
    with pytest.raises(PayloadDecodeError):
        parse_components([{"content": "no type"}])
    with pytest.raises(PayloadDecodeError):
        parse_components([{"type": True}])


def test_received_components_survive_a_msgpack_snapshot() -> None:
    message = {
        "id": "1",
        "channel_id": "2",
        "author": {"id": "3", "username": "u", "discriminator": "0", "global_name": None, "avatar": None},
        "content": "",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "edited_timestamp": None,
        "tts": False,
        "mention_everyone": False,
        "mentions": [],
        "mention_roles": [],
        "attachments": [],
        "embeds": [],
        "pinned": False,
        "type": 0,
        "components": [{"type": 11, "media": {"url": "https://x", "flags": 1}}],
    }
    decoded = decode_json(msgspec.json.encode(message), Message)
    restored = decode_msgpack(encode_msgpack(decoded), Message)
    assert not isinstance(restored.components, msgspec.UnsetType)
    [thumbnail] = parse_components(restored.components)
    assert isinstance(thumbnail, Thumbnail)
    assert thumbnail.media.flags == UnfurledMediaItemFlags(is_animated=True)


def test_media_items_report_what_discord_adds() -> None:
    item = decode_json(
        b'{"url":"https://x","proxy_url":"https://p","height":null,"width":10,"content_type":"image/png"}',
        UnfurledMediaItem,
    )
    assert item.height is None
    assert item.width == 10
