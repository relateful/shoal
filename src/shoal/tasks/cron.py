"""Cron expressions: five fields, evaluated in a time zone.

    Cron.parse("0 9 * * MON-FRI").next_after(now)            # 09:00 UTC on weekdays
    Cron.parse("*/15 * * * *", tz="Europe/Paris")             # every quarter hour, Paris time

Fields are minute, hour, day of month, month and day of week, each `*`, a value, a range (`1-5`), a
list (`1,15`) or a step (`*/10`, `5-50/5`). Months and days take names (`JAN`, `MON`); Sunday is `0`
or `7`. As in classic cron, when both day fields are restricted a day matches either.

A local time skipped by a daylight saving change runs as if the clock had not jumped (02:30 runs at
03:30); a time that happens twice runs once, the first time.
"""

from datetime import UTC, datetime, timedelta, tzinfo
from typing import Final, final, override
from zoneinfo import ZoneInfo

_MONTHS: Final = {
    name: number
    for number, name in enumerate(
        ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), start=1
    )
}
_DAYS: Final = {name: number for number, name in enumerate(("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"))}

_SEARCH_YEARS: Final = 5
"""How far ahead a schedule is searched before it is taken to never match (`0 0 30 2 *`)."""


def _field(text: str, low: int, high: int, names: dict[str, int] | None = None) -> frozenset[int]:
    values: set[int] = set()
    for part in text.split(","):
        body, _, step_text = part.partition("/")
        step = int(step_text) if step_text else 1
        if step < 1:
            msg = f"cron step must be at least 1: {part!r}"
            raise ValueError(msg)
        if body == "*":
            start, end = low, high
        else:
            first, _, last = body.partition("-")
            start = _value(first, names)
            end = _value(last, names) if last else (high if step_text else start)
        if not low <= start <= end <= high:
            msg = f"cron field {part!r} is outside {low}-{high}"
            raise ValueError(msg)
        values.update(range(start, end + 1, step))
    return frozenset(values)


def _value(text: str, names: dict[str, int] | None) -> int:
    if names is not None and text.upper() in names:
        return names[text.upper()]
    try:
        return int(text)
    except ValueError:
        msg = f"not a cron value: {text!r}"
        raise ValueError(msg) from None


@final
class Cron:
    """A parsed cron expression; `next_after` finds when it next fires.

    Use `Cron.parse`.
    """

    __slots__ = (
        "_days",
        "_dom_any",
        "_dow_any",
        "_hours",
        "_minutes",
        "_months",
        "_weekdays",
        "expression",
        "tz",
    )

    def __init__(self, expression: str, tz: tzinfo) -> None:
        """Parse `expression`; see `Cron.parse`."""
        fields = expression.split()
        if len(fields) != 5:  # noqa: PLR2004 - minute, hour, day, month, weekday
            msg = f"a cron expression has five fields: {expression!r}"
            raise ValueError(msg)
        minute, hour, day, month, weekday = fields
        self.expression: str = expression
        self.tz: tzinfo = tz
        self._minutes: frozenset[int] = _field(minute, 0, 59)
        self._hours: frozenset[int] = _field(hour, 0, 23)
        self._days: frozenset[int] = _field(day, 1, 31)
        self._months: frozenset[int] = _field(month, 1, 12, _MONTHS)
        self._weekdays: frozenset[int] = frozenset(day % 7 for day in _field(weekday, 0, 7, _DAYS))
        self._dom_any: bool = day == "*"
        self._dow_any: bool = weekday == "*"

    @classmethod
    def parse(cls, expression: str, *, tz: str | tzinfo | None = None) -> "Cron":
        """Parse a five-field cron expression, evaluated in `tz` (a zone name, or UTC).

        Raises:
            ValueError: The expression is not valid cron.
            zoneinfo.ZoneInfoNotFoundError: `tz` names no known zone.
        """
        zone = UTC if tz is None else ZoneInfo(tz) if isinstance(tz, str) else tz
        return cls(expression, zone)

    def next_after(self, moment: datetime) -> datetime:
        """The first time strictly after `moment` the expression fires, in UTC.

        Raises:
            ValueError: `moment` is naive, or the expression never fires (`0 0 30 2 *`).
        """
        if moment.tzinfo is None:
            msg = "cron needs an aware datetime"
            raise ValueError(msg)
        local = moment.astimezone(self.tz).replace(tzinfo=None, second=0, microsecond=0) + timedelta(
            minutes=1
        )
        # A year bound, not `replace(year=...)`: that raises on February 29.
        last_year = local.year + _SEARCH_YEARS
        while local.year <= last_year:
            if local.month not in self._months:
                local = _next_month(local)
            elif not self._day_matches(local):
                local = (local + timedelta(days=1)).replace(hour=0, minute=0)
            elif local.hour not in self._hours:
                local = (local + timedelta(hours=1)).replace(minute=0)
            elif local.minute not in self._minutes:
                local += timedelta(minutes=1)
            else:
                fired = local.replace(tzinfo=self.tz).astimezone(UTC)
                if fired > moment:
                    return fired
                # The repeated hour of a fall-back: this local time first came before `moment`.
                local += timedelta(minutes=1)
        msg = f"cron expression {self.expression!r} never fires"
        raise ValueError(msg)

    def _day_matches(self, local: datetime) -> bool:
        in_month = local.day in self._days
        in_week = (local.isoweekday() % 7) in self._weekdays
        if self._dom_any or self._dow_any:
            return in_month and in_week
        return in_month or in_week

    @override
    def __repr__(self) -> str:
        """`Cron('0 9 * * MON', tz=UTC)`."""
        return f"Cron({self.expression!r}, tz={self.tz})"


def _next_month(local: datetime) -> datetime:
    if local.month == 12:  # noqa: PLR2004 - December
        return local.replace(year=local.year + 1, month=1, day=1, hour=0, minute=0)
    return local.replace(month=local.month + 1, day=1, hour=0, minute=0)
