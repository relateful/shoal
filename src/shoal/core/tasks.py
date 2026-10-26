"""Background tasks: started without being lost, stopped without losing errors."""

import asyncio
import logging
from collections.abc import Coroutine

_log = logging.getLogger("shoal")

_RUNNING: set[asyncio.Task[None]] = set()
"""Tasks started with `spawn`, kept so they are not garbage collected before they finish."""


def spawn(coroutine: Coroutine[object, object, None], *, name: str) -> asyncio.Task[None]:
    """Run `coroutine` in the background until it ends; a failure is logged, never lost.

    Needs a running event loop.
    """
    task = asyncio.get_running_loop().create_task(coroutine, name=name)
    _RUNNING.add(task)
    task.add_done_callback(_finished)
    return task


def _finished(task: asyncio.Task[None]) -> None:
    _RUNNING.discard(task)
    if not task.cancelled() and (error := task.exception()) is not None:
        _log.error("background task %s failed", task.get_name(), exc_info=error)


async def cancel_and_wait[T](task: asyncio.Task[T]) -> BaseException | None:
    """Cancel `task`, wait for it to finish, and return the exception it ended with, if any.

    The task's own cancellation is expected and not returned. If the *caller* is cancelled while
    waiting, that cancellation propagates instead of being mistaken for the task's.
    """
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            raise
    except Exception as error:  # noqa: BLE001 - handed to the caller, which decides what to do with it
        return error
    return None
