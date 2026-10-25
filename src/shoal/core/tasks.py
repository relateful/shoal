"""Stopping background tasks without losing errors or swallowing the caller's own cancellation."""

import asyncio


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
