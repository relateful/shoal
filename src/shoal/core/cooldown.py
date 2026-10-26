"""Sliding-window cooldowns: at most `rate` uses per `per` seconds for each key.

    cooldown = Cooldown[Interaction](1, 10.0, key=lambda interaction: interaction.user.id)
    wait = cooldown.update_rate_limit(interaction)  # records a use; 0.0 when allowed

Slash commands key them on an interaction, prefix commands on a context. State lives in the process:
with several processes, each counts on its own.
"""

from collections.abc import Callable, Hashable

from shoal.core.clock import Clock, SystemClock
from shoal.core.defaults import COOLDOWN_PRUNE_ABOVE, COOLDOWN_PRUNE_INTERVAL


class Cooldown[T]:
    """`rate` uses per `per` seconds for each key `key` gives a subject (a user, a guild, ...)."""

    __slots__ = ("_clock", "_pruned", "_uses", "key", "per", "rate")

    def __init__(
        self, rate: int, per: float, *, key: Callable[[T], Hashable], clock: Clock | None = None
    ) -> None:
        """A cooldown allowing `rate` uses per `per` seconds.

        Raises:
            ValueError: `rate` is below 1 or `per` is not positive.
        """
        if rate < 1 or per <= 0:
            msg = f"a cooldown needs rate >= 1 and per > 0, not {rate} per {per}"
            raise ValueError(msg)
        self.rate: int = rate
        self.per: float = per
        self.key: Callable[[T], Hashable] = key
        self._clock: Clock = clock or SystemClock()
        self._uses: dict[Hashable, list[float]] = {}
        self._pruned: float = self._clock.monotonic()

    @property
    def tracked(self) -> int:
        """How many keys the cooldown is holding uses for."""
        return len(self._uses)

    def get_retry_after(self, subject: T) -> float:
        """Seconds until `subject` may use it again, without recording a use; 0.0 when allowed now."""
        now = self._clock.monotonic()
        uses = [moment for moment in self._uses.get(self.key(subject), ()) if moment > now - self.per]
        return uses[0] + self.per - now if len(uses) >= self.rate else 0.0

    def update_rate_limit(self, subject: T) -> float:
        """Record a use by `subject` when allowed; returns 0.0 then, or the seconds until it would be."""
        now = self._clock.monotonic()
        if len(self._uses) > COOLDOWN_PRUNE_ABOVE and now - self._pruned >= min(
            self.per, COOLDOWN_PRUNE_INTERVAL
        ):
            # Not on every use, so a busy cooldown does not scan every key each time.
            self._uses = {key: uses for key, uses in self._uses.items() if uses[-1] > now - self.per}
            self._pruned = now
        key = self.key(subject)
        uses = [moment for moment in self._uses.get(key, ()) if moment > now - self.per]
        if len(uses) >= self.rate:
            self._uses[key] = uses
            return uses[0] + self.per - now
        uses.append(now)
        self._uses[key] = uses
        return 0.0

    def reset(self, subject: T) -> None:
        """Forget `subject`'s uses, so its next use is allowed."""
        self._uses.pop(self.key(subject), None)
