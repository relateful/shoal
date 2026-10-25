from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from shoal.core.snowflake import DISCORD_EPOCH_MS, UINT64_MAX, Snowflake

DOCS_EXAMPLE = 175928847299117063


def test_decodes_the_documented_example() -> None:
    snowflake = Snowflake("175928847299117063")
    assert snowflake == DOCS_EXAMPLE
    assert snowflake.timestamp_ms == 1462015105796
    assert snowflake.created_at == datetime(2016, 4, 30, 11, 18, 25, 796000, tzinfo=UTC)
    assert snowflake.worker_id == 1
    assert snowflake.process_id == 0
    assert snowflake.increment == 7


def test_behaves_like_an_int() -> None:
    snowflake = Snowflake(DOCS_EXAMPLE)
    assert isinstance(snowflake, int)
    assert hash(snowflake) == hash(DOCS_EXAMPLE)
    lookup: dict[int, str] = {snowflake: "x"}
    assert lookup[DOCS_EXAMPLE] == "x"
    assert str(snowflake) == "175928847299117063"
    assert repr(snowflake) == "Snowflake(175928847299117063)"


@pytest.mark.parametrize("value", ["-1", "12a", "", " 1", "1.5", "١٢"])
def test_rejects_non_decimal_strings(value: str) -> None:
    with pytest.raises(ValueError, match="decimal"):
        Snowflake(value)


@pytest.mark.parametrize("value", [-1, UINT64_MAX + 1])
def test_rejects_out_of_range(value: int) -> None:
    with pytest.raises(ValueError, match="64-bit"):
        Snowflake(value)


def test_rejects_bool() -> None:
    with pytest.raises(TypeError):
        Snowflake(True)


def test_accepts_the_full_unsigned_range() -> None:
    assert Snowflake(0) == 0
    assert Snowflake(UINT64_MAX) == UINT64_MAX


def test_from_datetime_brackets_every_id_of_that_millisecond() -> None:
    moment = Snowflake(DOCS_EXAMPLE).created_at
    low = Snowflake.from_datetime(moment)
    high = Snowflake.from_datetime(moment, high=True)
    assert low <= DOCS_EXAMPLE <= high
    assert low.created_at == high.created_at == moment


def test_from_datetime_requires_an_aware_datetime_after_the_epoch() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Snowflake.from_datetime(datetime(2020, 1, 1))  # noqa: DTZ001
    with pytest.raises(ValueError, match="epoch"):
        Snowflake.from_datetime(datetime(2014, 12, 31, tzinfo=UTC))


@given(st.integers(min_value=0, max_value=UINT64_MAX))
def test_fields_reassemble_to_the_original(value: int) -> None:
    snowflake = Snowflake(value)
    rebuilt = (
        ((snowflake.timestamp_ms - DISCORD_EPOCH_MS) << 22)
        | (snowflake.worker_id << 17)
        | (snowflake.process_id << 12)
        | snowflake.increment
    )
    assert rebuilt == value


NAIVE_BOUNDS = (datetime(2015, 1, 2), datetime(2090, 1, 1))  # noqa: DTZ001 - hypothesis needs naive bounds with timezones=


@given(st.datetimes(min_value=NAIVE_BOUNDS[0], max_value=NAIVE_BOUNDS[1], timezones=st.just(UTC)))
def test_from_datetime_round_trips_to_the_millisecond(moment: datetime) -> None:
    created = Snowflake.from_datetime(moment).created_at
    assert abs(created - moment) < timedelta(milliseconds=1)
