import pytest

from shoal.core.flags import BaseFlags, flag


class Sample(BaseFlags):
    __slots__ = ()

    first = flag(0)
    third = flag(2)


def test_keyword_construction_and_attribute_reads() -> None:
    sample = Sample(first=True)
    assert sample == 1
    assert sample.first is True
    assert sample.third is False


def test_class_attribute_is_the_bit_value() -> None:
    assert Sample.first == 1
    assert Sample.third == 4
    assert Sample(Sample.first | Sample.third) == 5


def test_operators_keep_the_subclass() -> None:
    combined = Sample(first=True) | Sample.third
    assert isinstance(combined, Sample)
    assert combined.third
    assert isinstance(combined & Sample.first, Sample)
    assert isinstance(combined ^ Sample.first, Sample)
    assert isinstance(Sample.first | Sample(third=True), Sample)
    assert combined.without(Sample.first) == Sample(third=True)


def test_invert_keeps_bits_shoal_does_not_know() -> None:
    inverted = ~Sample(first=True)
    assert inverted.third
    assert not inverted.first
    newer = Sample(1 | 8)
    assert newer & ~Sample(first=True) == Sample(8)


def test_unknown_bits_are_kept_and_reported() -> None:
    sample = Sample(1 | 8)
    assert sample.unknown_bits == 8
    assert int(sample) == 9
    assert repr(sample) == "Sample(first|0x8)"
    assert repr(Sample(8)) == "Sample(0x8)"
    assert repr(Sample()) == "Sample(0)"


def test_keyword_overrides_raw_value() -> None:
    assert Sample(5, first=False) == 4
    assert Sample(0).with_flags(third=True) == 4


def test_has_requires_every_bit() -> None:
    sample = Sample(first=True, third=True)
    assert sample.has(Sample.first | Sample.third)
    assert not Sample(first=True).has(Sample.first | Sample.third)


def test_enabled_lists_names_in_bit_order() -> None:
    assert list(Sample(5).enabled()) == ["first", "third"]


def test_all_and_none() -> None:
    assert Sample.all() == 5
    assert Sample.none() == 0


@pytest.mark.parametrize("value", ["-1", "abc", ""])
def test_rejects_bad_strings(value: str) -> None:
    with pytest.raises(ValueError, match="decimal"):
        Sample(value)


def test_rejects_unknown_keywords_bools_and_range() -> None:
    with pytest.raises(TypeError, match="not a valid Sample flag"):
        Sample(second=True)
    with pytest.raises(TypeError):
        Sample(True)
    with pytest.raises(ValueError, match="64-bit"):
        Sample(1 << 64)
    with pytest.raises(ValueError, match="shift"):
        flag(64)


def test_subclass_inherits_parent_flags() -> None:
    class Extended(Sample):
        __slots__ = ()
        fifth = flag(4)

    assert Extended.known_flags == {"first": 1, "third": 4, "fifth": 16}
    assert Extended.all() == 21
