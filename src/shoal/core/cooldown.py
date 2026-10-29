"""Sliding-window cooldowns: at most `rate` uses per `per` seconds for each key.

    cooldown = Cooldown[Interaction](1, 10.0, key=lambda interaction: interaction.user.id)
    wait = cooldown.update_rate_limit(interaction)  # records a use; 0.0 when allowed

A `DynamicCooldown` chooses the limit per key, from the first use with that key:

    def per_role(ctx: Context) -> Cooldown[Context] | None:
        return None if ctx.author.has_role(VIP) else Cooldown(1, 30.0)

Slash commands key them on an interaction, prefix commands on a context. State lives in the process:
with several processes, each counts on its own.
"""

from collections.abc import Callable, Hashable

from shoal.core.clock import Clock, SystemClock
from shoal.core.defaults import COOLDOWN_PRUNE_ABOVE, COOLDOWN_PRUNE_INTERVAL


def _together(subject: object) -> Hashable:
    """One key for every subject: the cooldown is shared by all of them."""
    del subject
    return None


class Cooldown[T]:
    """`rate` uses per `per` seconds for each key `key` gives a subject (a user, a guild, ...).

    Without `key`, every subject shares one count.
    """

    __slots__ = ("_clock", "_pruned", "_uses", "key", "per", "rate")

    def __init__(
        self, rate: int, per: float, *, key: Callable[[T], Hashable] | None = None, clock: Clock | None = None
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
        self.key: Callable[[T], Hashable] = key or _together
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
        return _remaining(uses[0], self.per, now) if len(uses) >= self.rate else 0.0

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
            return _remaining(uses[0], self.per, now)
        uses.append(now)
        self._uses[key] = uses
        return 0.0

    def reset(self, subject: T) -> None:
        """Forget `subject`'s uses, so its next use is allowed."""
        self._uses.pop(self.key(subject), None)

    def is_idle(self) -> bool:
        """Whether no use is recent enough to count any more."""
        since = self._clock.monotonic() - self.per
        return all(uses[-1] <= since for uses in self._uses.values() if uses)


class DynamicCooldown[T]:
    """A cooldown whose limit `factory` chooses for each key, from the first use with that key.

    `factory` returns a `Cooldown` (only its `rate` and `per` count), or `None` for no limit; it
    is asked again for a key once that key's uses have all expired.
    """

    __slots__ = ("_buckets", "_clock", "_pruned", "factory", "key")

    def __init__(
        self,
        factory: Callable[[T], Cooldown[T] | None],
        *,
        key: Callable[[T], Hashable] | None = None,
        clock: Clock | None = None,
    ) -> None:
        """A cooldown limited per `key` (every subject together without one) as `factory` decides."""
        self.factory: Callable[[T], Cooldown[T] | None] = factory
        self.key: Callable[[T], Hashable] = key or _together
        self._clock: Clock = clock or SystemClock()
        self._buckets: dict[Hashable, Cooldown[T]] = {}
        self._pruned: float = self._clock.monotonic()

    @property
    def tracked(self) -> int:
        """How many keys the cooldown is holding uses for."""
        return len(self._buckets)

    def _bucket(self, subject: T) -> Cooldown[T] | None:
        key = self.key(subject)
        found = self._buckets.get(key)
        if found is not None:
            return found
        chosen = self.factory(subject)
        if chosen is None:
            return None
        bucket = Cooldown[T](chosen.rate, chosen.per, clock=self._clock)
        self._buckets[key] = bucket
        return bucket

    def get_retry_after(self, subject: T) -> float:
        """Seconds until `subject` may use it again, without recording a use; 0.0 when allowed now."""
        found = self._buckets.get(self.key(subject))
        return 0.0 if found is None else found.get_retry_after(subject)

    def update_rate_limit(self, subject: T) -> float:
        """Record a use by `subject` when allowed; returns 0.0 then, or the seconds until it would be."""
        now = self._clock.monotonic()
        if len(self._buckets) > COOLDOWN_PRUNE_ABOVE and now - self._pruned >= COOLDOWN_PRUNE_INTERVAL:
            # Not on every use, so a busy cooldown does not scan every key each time.
            self._buckets = {key: bucket for key, bucket in self._buckets.items() if not bucket.is_idle()}
            self._pruned = now
        bucket = self._bucket(subject)
        return 0.0 if bucket is None else bucket.update_rate_limit(subject)

    def reset(self, subject: T) -> None:
        """Forget `subject`'s uses (and its limit), so its next use is allowed."""
        self._buckets.pop(self.key(subject), None)


type AnyCooldown[T] = Cooldown[T] | DynamicCooldown[T]
"""A cooldown with a fixed limit, or one chosen per key."""


def _remaining(first: float, per: float, now: float) -> float:
    """Seconds left in the window that started at `first`, never above `per`.

    `first + per - now` rounds above `per` at large clock values (Windows CI saw 60.00000000000003
    for a 60 s cooldown); subtracting first keeps the result within the window.
    """
    return (first - now) + per
