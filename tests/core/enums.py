import pytest

from shoal.core.codec import PayloadDecodeError, decode_json
from shoal.payloads import ChannelType, GuildFeature
from tests.support.calls import call_unchecked


def test_unknown_int_enum_value_decodes_to_a_cached_pseudo_member() -> None:
    first = decode_json(b"99", ChannelType)
    assert first is ChannelType(99)
    assert first == 99
    assert first.name == "UNKNOWN_99"
    assert not first.is_known
    assert ChannelType.GUILD_TEXT.is_known
    assert first not in list(ChannelType)


def test_unknown_str_enum_value_decodes() -> None:
    feature = decode_json(b'"SHINY_NEW_THING"', GuildFeature)
    assert feature == "SHINY_NEW_THING"
    assert not feature.is_known
    assert feature is GuildFeature("SHINY_NEW_THING")


def test_open_enums_reject_values_of_the_wrong_json_type() -> None:
    with pytest.raises(PayloadDecodeError):
        decode_json(b'"0"', ChannelType)
    with pytest.raises(PayloadDecodeError):
        decode_json(b"5", GuildFeature)


def test_values_of_the_wrong_python_type_are_not_turned_into_members() -> None:
    with pytest.raises(ValueError, match="is not a valid ChannelType"):
        call_unchecked(ChannelType, "0")
    with pytest.raises(ValueError, match="is not a valid GuildFeature"):
        call_unchecked(GuildFeature, 5)
