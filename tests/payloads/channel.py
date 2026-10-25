from shoal.core.codec import decode_json
from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    OBFUSCATED_RELIABLE_FIELDS,
    Channel,
    ChannelFlags,
    ChannelType,
)


def test_obfuscated_channel_hides_its_name() -> None:
    raw = (
        b'{"id":"1","type":0,"guild_id":"2","position":3,"parent_id":"4","name":"___hidden___",'
        b'"flags":131072,"permission_overwrites":[{"id":"2","type":0,"allow":"0","deny":"1024"}]}'
    )
    channel = decode_json(raw, Channel)
    assert channel.is_obfuscated
    assert channel.visible_name is None
    assert channel.name == "___hidden___"
    assert {"id", "type", "position", "parent_id"} == OBFUSCATED_RELIABLE_FIELDS


def test_visible_channel_reports_its_name() -> None:
    channel = Channel(id=Snowflake(1), type=ChannelType.GUILD_TEXT, name="general", flags=ChannelFlags())
    assert not channel.is_obfuscated
    assert channel.visible_name == "general"
    assert Channel(id=Snowflake(1), type=ChannelType.DM).visible_name is None
