import msgspec

from shoal.core import UNSET
from shoal.core.codec import decode_json, encode_json
from shoal.payloads import (
    GuildCreate,
    Identify,
    IdentifyConnectionProperties,
    Intents,
    MessageCreate,
    Ready,
)


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
