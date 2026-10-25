"""Injectable time, so rate limiters, heartbeats and cache TTLs are testable without sleeping."""

import asyncio
import time
from typing import Protocol, final, override


class Clock(Protocol):
    """A source of time and a way to wait."""

    def monotonic(self) -> float:
        """Seconds on a clock that never goes backwards, for measuring intervals."""
        ...

    def wall(self) -> float:
        """Seconds since the Unix epoch, for values that must survive a restart."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Wait for `seconds` (returns immediately for zero or negative values)."""
        ...


@final
class SystemClock(Clock):
    """The real clock, backed by `time` and `asyncio.sleep`."""

    __slots__ = ()

    @override
    def monotonic(self) -> float:
        return time.monotonic()

    @override
    def wall(self) -> float:
        return time.time()

    @override
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(max(seconds, 0.0))


async def sleep_unless(clock: Clock, seconds: float, stop: asyncio.Event) -> None:
    """Sleep for `seconds` on `clock`, waking early once `stop` is set.

    Reconnect loops wait through this, so shutting down never waits out a backoff.
    """
    if stop.is_set():
        return
    sleeper = asyncio.ensure_future(clock.sleep(seconds))
    stopped = asyncio.ensure_future(stop.wait())
    try:
        await asyncio.wait({sleeper, stopped}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        sleeper.cancel()
        stopped.cancel()
    if sleeper.done() and not sleeper.cancelled() and sleeper.exception() is not None:
        await sleeper  # a failing clock is an error to raise now, not a warning at shutdown
