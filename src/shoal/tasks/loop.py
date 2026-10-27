"""Background loops: a function run every interval or at times of day.

    class Status(commands.Cog):
        @tasks.loop(minutes=5)
        async def refresh(self) -> None: ...

        @refresh.before_loop
        async def before(self) -> None:
            await self.bot.wait_until_ready()

        async def cog_load(self) -> None:
            self.refresh.start()

Iterations keep to an absolute schedule (`started + n * interval`), so a slow iteration does not push
every later one back; one that overran its slot is not caught up with a burst. With `time=` the loop
runs at those times of day instead. These loops live in this process; for work that must survive a
restart (a reminder in three days), use the `Scheduler`.
"""

import asyncio
import datetime as dt
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Self, final, overload

from shoal.core.clock import Clock, SystemClock
from shoal.core.tasks import spawn

_log = logging.getLogger("shoal.tasks")

type LoopFunction = Callable[..., Awaitable[None]]


@final
class Loop:
    """A function run over and over in the background; made by `loop`.

    On a class, each instance gets its own loop (`self.refresh` is not shared between cogs).
    """

    __slots__ = (
        "_after",
        "_before",
        "_clock",
        "_count",
        "_error",
        "_function",
        "_instance",
        "_interval",
        "_last_start",
        "_next",
        "_replan",
        "_stopping",
        "_task",
        "_times",
        "current_loop",
    )

    def __init__(
        self,
        function: LoopFunction,
        *,
        interval: float,
        times: Sequence[dt.time],
        count: int | None,
        clock: Clock,
    ) -> None:
        """Create a stopped loop; use `loop`."""
        self._function: LoopFunction = function
        self._interval: float = interval
        self._times: tuple[dt.time, ...] = _aware(times)
        self._count: int | None = count
        self._clock: Clock = clock
        self._before: LoopFunction | None = None
        self._after: LoopFunction | None = None
        self._error: Callable[..., Awaitable[None]] | None = None
        self._instance: object = None
        self._task: asyncio.Task[None] | None = None
        self._stopping: bool = False
        self._replan: bool = False
        """Set by `change_interval`: the next wait counts slots of the new interval."""
        self._last_start: float = 0.0
        """When the current iteration started."""
        self._next: dt.datetime | None = None
        self.current_loop: int = 0
        """How many iterations have finished."""

    @overload
    def __get__(self, instance: None, owner: type) -> Self: ...
    @overload
    def __get__(self, instance: object, owner: type) -> "Loop": ...
    def __get__(self, instance: object, owner: type) -> "Loop":
        """The loop for `instance`, made the first time it is read."""
        if instance is None:
            return self
        bound = Loop(
            self._function, interval=self._interval, times=self._times, count=self._count, clock=self._clock
        )
        bound._before, bound._after, bound._error = self._before, self._after, self._error
        bound._instance = instance
        # Stored on the instance, it shadows this descriptor: later reads get the same loop, and it
        # goes away with the instance.
        vars(instance)[self._function.__name__] = bound
        return bound

    @property
    def next_iteration(self) -> dt.datetime | None:
        """When the next iteration starts (UTC), while running."""
        return self._next if self.is_running() else None

    def is_running(self) -> bool:
        """Whether the loop's task is running."""
        return self._task is not None and not self._task.done()

    def get_task(self) -> asyncio.Task[None] | None:
        """The loop's task, once started."""
        return self._task

    def start(self, *args: object, **kwargs: object) -> asyncio.Task[None]:
        """Start the loop, calling the function with these arguments each time.

        Raises:
            RuntimeError: The loop is already running.
        """
        if self.is_running():
            msg = "the loop is already running"
            raise RuntimeError(msg)
        self._stopping = False
        self.current_loop = 0
        self._task = spawn(self._run(args, kwargs), name=f"shoal-loop-{self._function.__name__}")
        return self._task

    def stop(self) -> None:
        """Stop after the current iteration (`after_loop` still runs)."""
        self._stopping = True

    def cancel(self) -> None:
        """Cancel the loop now, mid-iteration if one is running."""
        if self._task is not None:
            self._task.cancel()

    def restart(self, *args: object, **kwargs: object) -> None:
        """Cancel the loop and start it again once it has ended."""
        task = self._task
        if task is None or task.done():
            _ = self.start(*args, **kwargs)
            return
        task.add_done_callback(lambda _: self.start(*args, **kwargs))
        task.cancel()

    def change_interval(
        self,
        *,
        seconds: float = 0,
        minutes: float = 0,
        hours: float = 0,
        time: dt.time | Sequence[dt.time] = (),
    ) -> None:
        """Run on a new interval or times of day from the next iteration on.

        Raises:
            ValueError: Both an interval and times given, or a negative interval.
        """
        self._interval, self._times = _schedule(seconds, minutes, hours, time)
        self._replan = True

    def before_loop[F: LoopFunction](self, function: F) -> F:
        """Register a function awaited once before the first iteration."""
        self._before = function
        return function

    def after_loop[F: LoopFunction](self, function: F) -> F:
        """Register a function awaited once the loop ends (stopped, cancelled, or failed)."""
        self._after = function
        return function

    def error[F: Callable[..., Awaitable[None]]](self, function: F) -> F:
        """Register a function given the exception when an iteration raises; the loop then ends."""
        self._error = function
        return function

    async def _call(self, function: Callable[..., Awaitable[None]], *args: object) -> None:
        if self._instance is not None:
            await function(self._instance, *args)
        else:
            await function(*args)

    async def _run(self, args: tuple[object, ...], kwargs: dict[str, object]) -> None:
        try:
            if self._before is not None:
                await self._call(self._before)
            started = self._clock.wall()
            slot = 0
            if self._times:
                await self._sleep_until(self._next_time(started))
            while not self._stopping:
                self._last_start = self._clock.wall()
                if self._instance is not None:
                    await self._function(self._instance, *args, **kwargs)
                else:
                    await self._function(*args, **kwargs)
                self.current_loop += 1
                if self._finished():
                    break
                now = self._clock.wall()
                if self._times:
                    await self._sleep_until(self._next_time(now))
                    continue
                if not self._interval:
                    await self._sleep_until(now)  # no interval: run again once others have run
                    continue
                if self._replanned():
                    # A new interval counts its slots from the iteration that changed it.
                    started, slot = self._last_start, 0
                # Keep to the schedule; skip slots an overrunning iteration already missed.
                slot = max(slot + 1, int((now - started) / self._interval) + 1)
                await self._sleep_until(started + slot * self._interval)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - an iteration's error ends the loop, reported
            if self._error is None:
                _log.exception("loop %s raised; it has stopped", self._function.__name__)
            else:
                await self._call(self._error, error)
        finally:
            self._next = None
            if self._after is not None:
                await self._call(self._after)

    def _finished(self) -> bool:
        """Read through a method: `stop` changes `_stopping` while an iteration is awaited."""
        return self._stopping or (self._count is not None and self.current_loop >= self._count)

    def _replanned(self) -> bool:
        """Whether `change_interval` ran since the last look (it runs while an iteration is awaited)."""
        replanned, self._replan = self._replan, False
        return replanned

    async def _sleep_until(self, moment: float) -> None:
        self._next = dt.datetime.fromtimestamp(moment, dt.UTC)
        await self._clock.sleep(max(0.0, moment - self._clock.wall()))

    def _next_time(self, now: float) -> float:
        """The earliest of the loop's times of day strictly after `now`."""
        today = dt.datetime.fromtimestamp(now, dt.UTC).date()
        candidates = (
            dt.datetime.combine(today + dt.timedelta(days=days), time).timestamp()
            for days in (-1, 0, 1, 2)  # a time zone can put a UTC day's time on the local day before or after
            for time in self._times
        )
        return min(moment for moment in candidates if moment > now)


def _aware(times: Sequence[dt.time]) -> tuple[dt.time, ...]:
    """Times of day with a time zone: UTC when naive."""
    return tuple(time if time.tzinfo is not None else time.replace(tzinfo=dt.UTC) for time in times)


def _schedule(
    seconds: float, minutes: float, hours: float, time: dt.time | Sequence[dt.time]
) -> tuple[float, tuple[dt.time, ...]]:
    times = (time,) if isinstance(time, dt.time) else tuple(time)
    interval = seconds + minutes * 60 + hours * 3600
    if interval < 0:
        msg = "a loop interval cannot be negative"
        raise ValueError(msg)
    if times and interval:
        msg = "give a loop either an interval or times of day, not both"
        raise ValueError(msg)
    return interval, _aware(times)


def loop(
    *,
    seconds: float = 0,
    minutes: float = 0,
    hours: float = 0,
    time: dt.time | Sequence[dt.time] = (),
    count: int | None = None,
    clock: Clock | None = None,
) -> Callable[[LoopFunction], Loop]:
    """Make a function a `Loop`, run every interval or at times of day (naive times are UTC).

    Args:
        seconds: The interval's seconds.
        minutes: The interval's minutes.
        hours: The interval's hours.
        time: Times of day to run at, instead of an interval.
        count: Stop after this many iterations; `None` runs until stopped.
        clock: Time source (tests pass a fake).

    Raises:
        ValueError: Both an interval and times given, a negative interval, or `count` below 1.
    """
    interval, times = _schedule(seconds, minutes, hours, time)
    if count is not None and count < 1:
        msg = "count must be at least 1"
        raise ValueError(msg)

    def decorate(function: LoopFunction) -> Loop:
        return Loop(function, interval=interval, times=times, count=count, clock=clock or SystemClock())

    return decorate
