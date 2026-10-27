from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from shoal.tasks.cron import Cron


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


@pytest.mark.parametrize(
    ("expression", "after", "expected"),
    [
        ("* * * * *", "2026-01-01T10:00:30", "2026-01-01T10:01:00"),
        ("0 9 * * *", "2026-01-01T09:00:00", "2026-01-02T09:00:00"),
        ("*/15 * * * *", "2026-01-01T10:16:00", "2026-01-01T10:30:00"),
        ("5-50/15 * * * *", "2026-01-01T10:21:00", "2026-01-01T10:35:00"),
        ("0 0 1,15 * *", "2026-01-02T00:00:00", "2026-01-15T00:00:00"),
        ("0 9 * * MON-FRI", "2026-01-02T09:00:00", "2026-01-05T09:00:00"),  # Friday to Monday
        ("0 0 * * 7", "2026-01-01T00:00:00", "2026-01-04T00:00:00"),  # 7 is Sunday
        ("0 0 1 JAN *", "2026-03-01T00:00:00", "2027-01-01T00:00:00"),
        ("0 0 29 2 *", "2026-03-01T00:00:00", "2028-02-29T00:00:00"),  # the next leap day
        ("0 0 31 12 *", "2026-12-31T00:00:00", "2027-12-31T00:00:00"),
    ],
)
def test_the_next_time_in_utc(expression: str, after: str, expected: str) -> None:
    assert Cron.parse(expression).next_after(at(after)) == at(expected)


def test_a_leap_day_is_searched_from() -> None:
    daily = Cron.parse("0 9 * * *")
    assert daily.next_after(at("2028-02-29T08:00:00")) == at("2028-02-29T09:00:00")


def test_the_repeated_hour_of_a_fall_back_never_gives_a_past_time() -> None:
    # 2026-11-01 in New York: 01:00-01:59 happens twice; 06:20Z is the second 01:20.
    quarter = Cron.parse("*/15 * * * *", tz="America/New_York")
    after = at("2026-11-01T06:20:00")
    fired = quarter.next_after(after)
    assert fired > after
    assert fired == at("2026-11-01T07:00:00")  # 02:00 EST: the repeated 01:xx ran the first time


def test_both_day_fields_restricted_match_either() -> None:
    # The 13th, or any Friday: Friday 2026-01-02 comes first.
    assert Cron.parse("0 0 13 * FRI").next_after(at("2026-01-01T00:00:00")) == at("2026-01-02T00:00:00")


def test_a_time_zone_shifts_the_schedule_and_follows_daylight_saving() -> None:
    paris = Cron.parse("0 9 * * *", tz="Europe/Paris")
    assert paris.next_after(at("2026-01-10T00:00:00")) == at("2026-01-10T08:00:00")  # UTC+1
    assert paris.next_after(at("2026-07-10T00:00:00")) == at("2026-07-10T07:00:00")  # UTC+2
    # 02:30 does not exist on 2026-03-29 in Paris: it runs as if the clock had not jumped.
    skipped = Cron.parse("30 2 * * *", tz=ZoneInfo("Europe/Paris"))
    assert skipped.next_after(at("2026-03-28T12:00:00")) == at("2026-03-29T01:30:00")


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("* * * *", "five fields"),
        ("60 * * * *", "outside 0-59"),
        ("*/0 * * * *", "step must be at least 1"),
        ("5-1 * * * *", "outside"),
        ("x * * * *", "not a cron value"),
    ],
)
def test_invalid_expressions_are_refused(expression: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _ = Cron.parse(expression)


def test_an_expression_that_never_fires_says_so() -> None:
    with pytest.raises(ValueError, match="never fires"):
        _ = Cron.parse("0 0 30 2 *").next_after(at("2026-01-01T00:00:00"))


def test_naive_moments_are_refused() -> None:
    with pytest.raises(ValueError, match="aware"):
        _ = Cron.parse("* * * * *").next_after(datetime(2026, 1, 1))  # noqa: DTZ001 - the case under test


def test_the_repr_names_the_expression_and_zone() -> None:
    assert repr(Cron.parse("0 9 * * MON")) == "Cron('0 9 * * MON', tz=UTC)"
