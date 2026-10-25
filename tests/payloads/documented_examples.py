"""Decode the example objects printed in Discord's own documentation.

`fixtures/discord_examples.json` is copied verbatim from the discord-api-docs repository
(https://github.com/discord/discord-api-docs, MIT licensed code samples).

Several examples predate fields that Discord's field tables mark as always present (for example
`global_name`, added in 2023, is missing from the message example). Shoal types follow the field
tables, because live payloads contain those fields. `KNOWN_OUTDATED` records each example that is
behind its table and the exact field it lacks; the test fails if an example breaks for any other reason
or if Discord fixes one, so the list never goes stale.
"""

from pathlib import Path

import msgspec
import pytest

from shoal.core import UNSET
from shoal.core.codec import PayloadDecodeError, decode_json, encode_json
from shoal.payloads import (
    Channel,
    ChannelType,
    Emoji,
    GatewayOpcode,
    GatewayPayload,
    Guild,
    GuildFeature,
    GuildMember,
    Hello,
    Message,
    MessageType,
    Payload,
    Role,
    UnavailableGuild,
    User,
)

type Json = dict[str, object]

EXAMPLES: dict[str, Json] = msgspec.json.decode(
    (Path(__file__).parent / "fixtures" / "discord_examples.json").read_bytes(), type=dict[str, Json]
)

CASES: list[tuple[str, type[Payload]]] = [
    ("user", User),
    ("guild", Guild),
    ("guild_member", GuildMember),
    ("unavailable_guild", UnavailableGuild),
    ("text_channel", Channel),
    ("thread_channel", Channel),
    ("message", Message),
    ("crossposted_message", Message),
    ("emoji", Emoji),
    ("role", Role),
]

KNOWN_OUTDATED: dict[str, str] = {
    "guild": "missing required field `nsfw_level`",
    "guild_member": "missing required field `id` - at `$.user`",
    "message": "missing required field `global_name` - at `$.author`",
    "crossposted_message": "missing required field `global_name` - at `$.author`",
    "emoji": "missing required field `global_name` - at `$.user`",
}


def raw(name: str) -> bytes:
    return msgspec.json.encode(EXAMPLES[name])


MISSING_TOP_LEVEL: dict[str, Json] = {
    "guild": {"nsfw_level": 0, "premium_progress_bar_enabled": False},
    "guild_member": {"flags": 0},
}
MISSING_USER_FIELDS: Json = {
    "id": "1",
    "username": "example",
    "discriminator": "0",
    "global_name": None,
    "avatar": None,
}


def completed(name: str) -> bytes:
    """The example with the fields its field table requires but the example predates filled in."""
    data = msgspec.json.decode(raw(name), type=Json)
    for key, value in MISSING_TOP_LEVEL.get(name, {}).items():
        data.setdefault(key, value)
    for key in ("author", "user"):
        nested = data.get(key)
        if nested is not None:
            user = msgspec.convert(nested, type=Json)
            data[key] = {**MISSING_USER_FIELDS, **user}
    return msgspec.json.encode(data)


@pytest.mark.parametrize(("name", "target"), CASES)
def test_examples_decode_or_fail_only_for_their_known_gap(name: str, target: type[Payload]) -> None:
    gap = KNOWN_OUTDATED.get(name)
    if gap is None:
        decode_json(raw(name), target)
        return
    with pytest.raises(PayloadDecodeError) as caught:
        decode_json(raw(name), target)
    assert gap in str(caught.value)


@pytest.mark.parametrize(("name", "target"), CASES)
def test_round_trip_preserves_every_modeled_field(name: str, target: type[Payload]) -> None:
    decoded = decode_json(completed(name), target)
    assert decode_json(encode_json(decoded), target) == decoded


def test_hello_example_is_a_full_gateway_payload() -> None:
    payload = decode_json(raw("hello"), GatewayPayload)
    assert payload.op is GatewayOpcode.HELLO
    assert decode_json(payload.d, Hello).heartbeat_interval == 45000


def test_user_example() -> None:
    user = decode_json(raw("user"), User)
    assert user.id == 80351110224678912
    assert user.global_name is None
    assert user.bot is UNSET
    assert user.flags is not UNSET
    assert user.flags.hypesquad_online_house_1


def test_guild_example() -> None:
    guild = decode_json(completed("guild"), Guild)
    assert guild.name
    assert all(isinstance(feature, GuildFeature) for feature in guild.features)


def test_message_example() -> None:
    message = decode_json(completed("message"), Message)
    assert message.type is MessageType.DEFAULT
    assert message.timestamp.tzinfo is not None


def test_thread_example() -> None:
    channel = decode_json(raw("thread_channel"), Channel)
    assert channel.type.is_thread
    assert channel.thread_metadata is not UNSET
    assert not ChannelType.GUILD_TEXT.is_thread
