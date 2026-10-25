import asyncio

import pytest

from shoal.core.tasks import cancel_and_wait


async def test_a_cancelled_task_returns_nothing() -> None:
    task = asyncio.create_task(asyncio.sleep(60))
    await asyncio.sleep(0)
    assert await cancel_and_wait(task) is None
    assert task.cancelled()


async def test_the_task_error_is_returned_not_raised() -> None:
    async def fail() -> None:
        msg = "broken"
        raise RuntimeError(msg)

    task = asyncio.create_task(fail())
    await asyncio.sleep(0)
    error = await cancel_and_wait(task)
    assert isinstance(error, RuntimeError)


async def test_the_callers_own_cancellation_propagates() -> None:
    child = asyncio.create_task(asyncio.sleep(60))
    entered = asyncio.Event()

    async def stubborn() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            entered.set()
            await asyncio.sleep(60)

    blocker = asyncio.create_task(stubborn())

    async def parent() -> None:
        await cancel_and_wait(blocker)

    await asyncio.sleep(0)
    waiting = asyncio.create_task(parent())
    await entered.wait()
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    child.cancel()
    blocker.cancel()
    await asyncio.gather(child, blocker, return_exceptions=True)
