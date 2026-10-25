import asyncio
import time

from shoal.core.clock import SystemClock, sleep_unless
from tests.support.fakes import ManualClock, settle

WINDOWS_TIMER_RESOLUTION = 0.016
"""The monotonic clock on Windows advances in steps of about 15.6 ms, so short sleeps can measure short."""


async def test_system_clock_reads_real_time_and_sleeps() -> None:
    clock = SystemClock()
    before = clock.monotonic()
    await clock.sleep(0.05)
    await clock.sleep(-1)
    assert clock.monotonic() - before >= 0.05 - WINDOWS_TIMER_RESOLUTION
    assert abs(clock.wall() - time.time()) < 1


async def test_sleep_unless_wakes_when_stopped() -> None:
    clock = ManualClock()
    stop = asyncio.Event()
    sleeping = asyncio.create_task(sleep_unless(clock, 60, stop))
    await settle()
    assert not sleeping.done()
    stop.set()
    await asyncio.wait_for(sleeping, timeout=1)
    await sleep_unless(clock, 60, stop)


async def test_sleep_unless_sleeps_the_full_time_otherwise() -> None:
    clock = ManualClock()
    sleeping = asyncio.create_task(sleep_unless(clock, 5, asyncio.Event()))
    await settle()
    await clock.advance(4)
    assert not sleeping.done()
    await clock.advance(1)
    await asyncio.wait_for(sleeping, timeout=1)
