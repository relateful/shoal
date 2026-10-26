import msgspec
import pytest

from shoal.core import UNSET
from shoal.core.codec import decode_json, encode_json
from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    DISPATCH_PAYLOADS,
    ChannelInfoField,
    GatewayOpcode,
    GuildCreate,
    Identify,
    IdentifyConnectionProperties,
    Intents,
    MessageCreate,
    RateLimited,
    Ready,
    RequestChannelInfo,
    RequestSoundboardSounds,
    VoiceChannelEffectSend,
)
from tests.support.dispatches import DISPATCH_SAMPLES


def test_identify_encodes_shard_tuple_and_intents_as_integer() -> None:
    identify = Identify(
        token="t",
        properties=IdentifyConnectionProperties(os="linux", browser="shoal", device="shoal"),
        shard=(1, 4),
        intents=Intents(guilds=True),
    )
    decoded = msgspec.json.decode(encode_json(identify))
    assert decoded["shard"] == [1, 4]
    assert decoded["intents"] == 1
    assert "presence" not in decoded


def test_ready_and_guild_create_decode() -> None:
    ready = decode_json(
        b'{"v":10,"user":{"id":"1","username":"b","discriminator":"0","global_name":null,"avatar":null,'
        b'"bot":true},"guilds":[{"id":"2","unavailable":true}],"session_id":"s",'
        b'"resume_gateway_url":"wss://r","shard":[0,1],"application":{"id":"3","flags":0}}',
        Ready,
    )
    assert ready.shard == (0, 1)
    assert ready.guilds[0].unavailable is True
    guild = decode_json(
        b'{"id":"2","name":"g","icon":null,"splash":null,"discovery_splash":null,"owner_id":"1",'
        b'"afk_channel_id":null,"afk_timeout":300,"verification_level":0,"default_message_notifications":0,'
        b'"explicit_content_filter":0,"roles":[],"emojis":[],"features":["COMMUNITY"],"mfa_level":0,'
        b'"application_id":null,"system_channel_id":null,"system_channel_flags":0,"rules_channel_id":null,'
        b'"vanity_url_code":null,"description":null,"banner":null,"premium_tier":0,"preferred_locale":"en-US",'
        b'"public_updates_channel_id":null,"nsfw_level":0,"premium_progress_bar_enabled":false,'
        b'"safety_alerts_channel_id":null,"joined_at":"2020-01-01T00:00:00+00:00","large":false,'
        b'"member_count":1,"members":[],"channels":[],"threads":[],'
        b'"stage_instances":[{"id":"8","guild_id":"2","channel_id":"9","topic":"t","privacy_level":2,'
        b'"discoverable_disabled":false,"guild_scheduled_event_id":null}],'
        b'"soundboard_sounds":[{"name":"quack","sound_id":"1","volume":1.0,"emoji_id":null,'
        b'"emoji_name":"q","available":true}]}',
        GuildCreate,
    )
    assert guild.member_count == 1
    assert guild.stage_instances[0].topic == "t"
    assert guild.soundboard_sounds[0].name == "quack"
    assert guild.guild_scheduled_events == []


def test_message_create_extra_fields_are_optional() -> None:
    message = decode_json(
        b'{"id":"1","channel_id":"2","author":{"id":"3","username":"u","discriminator":"0",'
        b'"global_name":null,"avatar":null},"content":"x","timestamp":"2024-01-01T00:00:00+00:00",'
        b'"edited_timestamp":null,"tts":false,"mention_everyone":false,"mentions":[],"mention_roles":[],'
        b'"attachments":[],"embeds":[],"pinned":false,"type":0,"guild_id":"4"}',
        MessageCreate,
    )
    assert message.guild_id == 4
    assert message.member is UNSET


@pytest.mark.parametrize("name", sorted(DISPATCH_PAYLOADS))
def test_every_dispatch_decodes_and_encodes_back(name: str) -> None:
    sample = DISPATCH_SAMPLES[name]
    decoded = decode_json(msgspec.json.encode(sample), DISPATCH_PAYLOADS[name])
    expected = msgspec.json.encode(sample).replace(b"+00:00", b"Z")
    assert msgspec.json.decode(encode_json(decoded)) == msgspec.json.decode(expected)


def test_every_sample_is_a_dispatch() -> None:
    assert sorted(DISPATCH_SAMPLES) == sorted(DISPATCH_PAYLOADS)


def test_resumed_and_interaction_create_are_decoded_elsewhere() -> None:
    assert "RESUMED" not in DISPATCH_PAYLOADS
    assert "INTERACTION_CREATE" not in DISPATCH_PAYLOADS


def test_rate_limited_reads_guild_member_metadata() -> None:
    limited = decode_json(msgspec.json.encode(DISPATCH_SAMPLES["RATE_LIMITED"]), RateLimited)
    assert limited.opcode is GatewayOpcode.REQUEST_GUILD_MEMBERS
    metadata = limited.guild_members_metadata()
    assert metadata is not None
    assert metadata.guild_id == 2
    assert metadata.nonce == "chunk-1"


def test_rate_limited_for_another_opcode_has_no_member_metadata() -> None:
    limited = decode_json(b'{"opcode":31,"retry_after":1.0,"meta":{"something":"new"}}', RateLimited)
    assert limited.guild_members_metadata() is None


def test_voice_effect_sound_id_may_be_an_integer() -> None:
    effect = decode_json(
        b'{"channel_id":"6","guild_id":"2","user_id":"1","sound_id":3,"sound_volume":1.0}',
        VoiceChannelEffectSend,
    )
    assert effect.sound_id == 3


@pytest.mark.parametrize(
    ("payload", "secret"),
    [
        (DISPATCH_SAMPLES["VOICE_SERVER_UPDATE"], "my_token"),
        (DISPATCH_SAMPLES["INVITE_CREATE"], "0vCdhLbwjZZTWZLD"),
        (DISPATCH_SAMPLES["INVITE_DELETE"], "0vCdhLbwjZZTWZLD"),
    ],
    ids=["voice token", "created invite code", "deleted invite code"],
)
def test_credentials_in_events_stay_out_of_repr(payload: dict[str, object], secret: str) -> None:
    name = next(key for key, value in DISPATCH_SAMPLES.items() if value is payload)
    decoded = decode_json(msgspec.json.encode(payload), DISPATCH_PAYLOADS[name])
    assert secret not in repr(decoded)


def test_soundboard_and_channel_info_requests_encode() -> None:
    sounds = RequestSoundboardSounds(guild_ids=[Snowflake(613425648685547541), Snowflake(81384788765712384)])
    assert msgspec.json.decode(encode_json(sounds)) == {
        "guild_ids": ["613425648685547541", "81384788765712384"]
    }
    info = RequestChannelInfo(
        guild_id=Snowflake(613425648685547541),
        fields=[ChannelInfoField.STATUS, ChannelInfoField.VOICE_START_TIME],
    )
    assert msgspec.json.decode(encode_json(info)) == {
        "guild_id": "613425648685547541",
        "fields": ["status", "voice_start_time"],
    }
