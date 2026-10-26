import operator
from typing import get_args

import pytest

from shoal.app_commands.models import Choice, Namespace, Range, RangeSpec
from shoal.payloads import ApplicationCommandOptionChoice
from tests.support.calls import call_unchecked


def test_a_choice_becomes_the_payload_discord_takes() -> None:
    assert Choice(name="Red", value="red").to_payload() == ApplicationCommandOptionChoice(
        name="Red", value="red"
    )


def test_a_range_annotates_its_type_with_the_bounds() -> None:
    annotated = Range[int, 1, 10]
    assert get_args(annotated) == (int, RangeSpec(1, 10))


def test_a_range_needs_a_supported_type_and_a_bound() -> None:
    with pytest.raises(TypeError, match="int, float or str"):
        call_unchecked(operator.getitem, Range, (bytes, 1, 2))
    with pytest.raises(TypeError, match="minimum, a maximum"):
        call_unchecked(operator.getitem, Range, (int, None, None))


def test_a_namespace_reads_missing_options_as_none() -> None:
    namespace = Namespace({"member": 3})
    assert namespace.member == 3
    assert namespace.reason is None
    assert "member" in namespace
    assert "reason" not in namespace
    assert repr(namespace) == "<Namespace member=3>"
    with pytest.raises(AttributeError):
        _ = namespace.__wrapped__
