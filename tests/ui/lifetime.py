import asyncio

from shoal.ui.lifetime import Lifetime
from tests.support.fakes import ManualClock, settle


def is_finished(lifetime: Lifetime) -> bool:
    """Read through a call: checkers would otherwise keep a narrowed value across awaits."""
    return lifetime.finished


async def test_it_times_out_after_going_unused_and_says_so() -> None:
    clock = ManualClock()
    timeouts: list[bool] = []
    finished: list[str] = []
    lifetime = Lifetime(10, clock=clock, on_timeout=lambda: timeouts.append(True))
    lifetime.when_finished(lambda: finished.append("store"))
    lifetime.restart()
    await settle()
    await clock.advance(6)
    lifetime.restart()
    await settle()
    await clock.advance(6)
    assert not is_finished(lifetime)
    await clock.advance(4)
    assert is_finished(lifetime)
    assert timeouts == [True]
    assert finished == ["store"]
    assert await lifetime.wait() is True


async def test_stopping_runs_each_callback_once_and_cancels_the_timer() -> None:
    clock = ManualClock()
    timeouts: list[bool] = []
    finished: list[str] = []
    lifetime = Lifetime(10, clock=clock, on_timeout=lambda: timeouts.append(True))
    lifetime.when_finished(lambda: finished.append("first"))
    lifetime.restart()
    await settle()
    lifetime.stop()
    lifetime.stop()
    lifetime.when_finished(lambda: finished.append("late"))
    await clock.advance(20)
    assert finished == ["first", "late"]
    assert timeouts == []
    assert await lifetime.wait() is False


async def test_a_waiter_learns_how_it_stopped() -> None:
    clock = ManualClock()
    lifetime = Lifetime(5, clock=clock)
    lifetime.restart()
    await settle()
    waiting = [asyncio.create_task(lifetime.wait()) for _ in range(2)]
    await settle()
    await clock.advance(5)
    assert [await wait for wait in waiting] == [True, True]


async def test_changing_the_timeout_while_running_restarts_it() -> None:
    clock = ManualClock()
    lifetime = Lifetime(100, clock=clock)
    lifetime.restart()
    await settle()
    lifetime.timeout = 1
    await settle()
    assert lifetime.timeout == 1
    await clock.advance(1)
    assert is_finished(lifetime)


async def test_without_a_timeout_or_before_it_is_sent_nothing_is_timed() -> None:
    clock = ManualClock()
    never = Lifetime(None, clock=clock)
    never.restart()
    await settle()
    unsent = Lifetime(1, clock=clock)
    unsent.timeout = 2
    await clock.advance(10)
    assert not is_finished(never)
    assert not is_finished(unsent)


def test_restarting_outside_an_event_loop_times_nothing() -> None:
    lifetime = Lifetime(1, clock=ManualClock())
    lifetime.restart()
    assert not is_finished(lifetime)
