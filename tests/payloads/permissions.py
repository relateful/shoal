from shoal.core.codec import decode_json, encode_json
from shoal.payloads import (
    MessageFlags,
    Permissions,
    RoleTags,
)


def test_permissions_wire_format_is_a_string() -> None:
    assert Permissions.WIRE_AS_STRING
    assert not MessageFlags.WIRE_AS_STRING
    assert Permissions("8").administrator


def test_role_tags_null_means_true() -> None:
    booster = decode_json(b'{"premium_subscriber":null}', RoleTags)
    assert booster.is_premium_subscriber
    assert not booster.is_available_for_purchase
    plain = decode_json(b'{"bot_id":"5"}', RoleTags)
    assert not plain.is_premium_subscriber
    assert not plain.is_guild_connection


def test_permissions_encode_as_a_string() -> None:
    raw = encode_json({"permissions": Permissions(administrator=True)})
    assert raw == b'{"permissions":"8"}'
