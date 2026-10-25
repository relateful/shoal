from msgspec import UNSET

from shoal.cache.guild import CachedGuild
from shoal.core.codec import decode_json, encode_json
from tests.cache.updater import guild_create


def test_a_guild_create_keeps_its_extra_fields_and_a_plain_guild_leaves_them_unset() -> None:
    created = decode_json(encode_json(guild_create()), CachedGuild)
    assert created.large is False
    assert created.member_count == 1
    plain = {
        key: value
        for key, value in guild_create().items()
        if key not in {"joined_at", "large", "member_count"}
    }
    guild = decode_json(encode_json(plain), CachedGuild)
    assert guild.joined_at is UNSET
    assert guild.member_count is UNSET
