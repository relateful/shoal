import asyncio
import datetime as dt

import pytest

from shoal.tasks.loop import loop
from tests.support.calls import call_unchecked
from tests.support.fakes import ManualClock, settle


async def test_iterations_keep_to_the_interval_and_stop_at_the_count() -> None:
    clock = ManualClock()
    ran: list[float] = []

    @loop(seconds=10, count=3, clock=clock)
    async def tick(label: str) -> None:
        assert label == "x"
        ran.append(clock.wall())

    task = tick.start("x")
    await settle()
    assert tick.is_running()
    assert tick.next_iteration == dt.datetime.fromtimestamp(ran[0] + 10, dt.UTC)
    for _ in range(2):
        await clock.advance(10)
        await settle()
    await task
    assert [moment - ran[0] for moment in ran] == [0, 10, 20]
    assert tick.current_loop == 3
    assert not tick.is_running()
    assert tick.next_iteration is None


async def test_a_slow_iteration_skips_the_slots_it_missed() -> None:
    clock = ManualClock()
    ran: list[float] = []

    @loop(seconds=10, count=3, clock=clock)
    async def slow() -> None:
        ran.append(clock.wall())
        if len(ran) == 1:
            await clock.sleep(25)  # overruns two slots

    task = slow.start()
    await settle()
    await clock.advance(25)
    await settle()
    await clock.advance(5)
    await settle()
    await clock.advance(10)
    await task
    assert [moment - ran[0] for moment in ran] == [0, 30, 40]


async def test_hooks_run_around_the_loop_and_errors_end_it() -> None:
    clock = ManualClock()
    events: list[str] = []

    @loop(seconds=1, clock=clock)
    async def failing() -> None:
        events.append("iteration")
        raise ValueError

    @failing.before_loop
    async def before() -> None:
        events.append("before")

    @failing.after_loop
    async def after() -> None:
        events.append("after")

    @failing.error
    async def error(raised: Exception) -> None:
        events.append(type(raised).__name__)

    await failing.start()
    assert events == ["before", "iteration", "ValueError", "after"]


async def test_an_unhandled_error_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    @loop(seconds=1, clock=ManualClock())
    async def failing() -> None:
        raise ValueError

    await failing.start()
    assert "loop failing raised; it has stopped" in caplog.text


async def test_stop_finishes_the_iteration_and_cancel_does_not() -> None:
    clock = ManualClock()
    ran: list[str] = []

    @loop(seconds=0, clock=clock)
    async def busy() -> None:
        ran.append("x")
        await clock.sleep(1)

    task = busy.start()
    await settle()
    busy.stop()
    await clock.advance(1)
    await task
    assert ran == ["x"]
    with pytest.raises(RuntimeError, match="already running"):
        _ = busy.start(), busy.start()
    busy.cancel()
    running = busy.get_task()
    assert running is not None
    with pytest.raises(asyncio.CancelledError):
        await running


async def test_restart_runs_again_from_the_first_iteration() -> None:
    clock = ManualClock()
    ran: list[int] = []

    @loop(seconds=5, clock=clock)
    async def counter() -> None:
        ran.append(counter.current_loop)

    counter.restart()  # not running yet: just starts
    await settle()
    await clock.advance(5)
    await settle()
    counter.restart()
    await settle()
    assert ran == [0, 1, 0]
    counter.cancel()
    await settle()


async def test_times_of_day_run_at_the_next_one() -> None:
    clock = ManualClock()  # 2025-06-15T15:06:40Z
    ran: list[dt.datetime] = []
    paris = dt.timezone(dt.timedelta(hours=2))

    @loop(time=[dt.time(18, 0, tzinfo=paris), dt.time(9, 0)], count=2, clock=clock)
    async def daily() -> None:
        ran.append(dt.datetime.fromtimestamp(clock.wall(), dt.UTC))

    task = daily.start()
    await settle()
    first = daily.next_iteration
    assert first is not None
    assert first == dt.datetime(2025, 6, 15, 16, 0, tzinfo=dt.UTC)
    await clock.advance(first.timestamp() - clock.wall())
    await settle()
    await clock.advance(17 * 3600)  # to 09:00 UTC the next day
    await task
    assert ran == [first, dt.datetime(2025, 6, 16, 9, 0, tzinfo=dt.UTC)]


async def test_each_instance_gets_its_own_loop() -> None:
    clock = ManualClock()

    class Cog:
        def __init__(self, name: str) -> None:
            self.name = name
            self.seen: list[str] = []

        @loop(seconds=1, count=1, clock=clock)
        async def work(self) -> None:
            self.seen.append(self.name)

    first, second = Cog("a"), Cog("b")
    assert first.work is first.work
    assert first.work is not second.work
    await first.work.start()
    assert (first.seen, second.seen) == (["a"], [])
    assert not second.work.is_running()


async def test_change_interval_applies_from_the_next_iteration() -> None:
    clock = ManualClock()
    ran: list[float] = []

    @loop(seconds=10, count=2, clock=clock)
    async def tick() -> None:
        ran.append(clock.wall())
        tick.change_interval(seconds=3)

    task = tick.start()
    await settle()
    await clock.advance(3)
    await task
    assert ran[1] - ran[0] == 3


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"seconds": -1}, "negative"),
        ({"seconds": 1, "time": dt.time(9)}, "not both"),
        ({"seconds": 1, "count": 0}, "count must be at least 1"),
    ],
)
def test_invalid_schedules_are_refused(arguments: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _ = call_unchecked(loop, **arguments)


async def test_a_longer_interval_counts_from_the_iteration_that_changed_it() -> None:
    clock = ManualClock()
    ran: list[float] = []

    @loop(seconds=1, count=12, clock=clock)
    async def tick() -> None:
        ran.append(clock.wall())
        if len(ran) == 10:
            tick.change_interval(hours=1)

    task = tick.start()
    for _ in range(9):
        await settle()
        await clock.advance(1)
    await settle()
    next_run = tick.next_iteration
    assert next_run is not None
    assert next_run.timestamp() - ran[-1] == 3600
    tick.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
