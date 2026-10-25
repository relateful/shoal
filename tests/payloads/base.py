import msgspec
import pytest

from shoal.core.codec import decode_json
from shoal.payloads.base import Payload
from tests.support.calls import call_unchecked


class Sample(Payload):
    optional: int | None = None
    required: str


def test_payloads_are_keyword_only_so_fields_keep_discord_order() -> None:
    assert Sample(required="x").optional is None
    with pytest.raises(TypeError):
        call_unchecked(Sample, "x")


def test_unknown_fields_from_discord_are_ignored() -> None:
    assert decode_json(b'{"required":"x","added_by_discord_later":1}', Sample) == Sample(required="x")


def test_payloads_skip_the_cycle_collector_by_default() -> None:
    assert Sample.__struct_config__.gc is False
    assert msgspec.Struct.__struct_config__.gc is True


def test_options_can_still_be_overridden() -> None:
    class Frozen(Payload, frozen=True):
        value: int

    field = "value"
    with pytest.raises(AttributeError):
        setattr(Frozen(value=1), field, 2)
