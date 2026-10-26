"""When a view or modal stops: when asked to, or once it has gone unused for its timeout."""

import asyncio
from collections.abc import Callable
from typing import final

from shoal.core.clock import Clock
from shoal.core.tasks import spawn


@final
class Lifetime:
    """Tracks whether a view or modal still receives interactions, and tells whoever keeps it.

    The timeout counts from the last `restart`; `None` never times out.
    """

    __slots__ = (
        "_clock",
        "_finished",
        "_on_finish",
        "_on_timeout",
        "_timed_out",
        "_timeout",
        "_timer",
        "_waiter",
    )

    def __init__(
        self, timeout: float | None, *, clock: Clock, on_timeout: Callable[[], object] | None = None
    ) -> None:
        """Start unfinished; `on_timeout` runs after a timeout stopped it."""
        self._timeout: float | None = timeout
        self._clock: Clock = clock
        self._on_timeout: Callable[[], object] | None = on_timeout
        self._finished: bool = False
        self._timed_out: bool = False
        self._timer: asyncio.Task[None] | None = None
        self._waiter: asyncio.Future[bool] | None = None
        self._on_finish: list[Callable[[], object]] = []

    @property
    def timeout(self) -> float | None:
        """Seconds without use before it stops."""
        return self._timeout

    @timeout.setter
    def timeout(self, value: float | None) -> None:
        self._timeout = value
        if self._timer is not None:
            self.restart()

    @property
    def finished(self) -> bool:
        """Whether it stopped or timed out."""
        return self._finished

    def restart(self) -> None:
        """Count the timeout from now. Without a running event loop there is nothing to time yet."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._timeout is None or self._finished:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        self._timer = spawn(self._expire_after(self._timeout), name="shoal-ui-timeout")

    async def _expire_after(self, seconds: float) -> None:
        await self._clock.sleep(seconds)
        self._timer = None
        self._timed_out = True
        self.stop()
        if self._on_timeout is not None:
            self._on_timeout()

    def stop(self) -> None:
        """Stop now; does nothing the second time."""
        if self._finished:
            return
        self._finished = True
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._waiter is not None and not self._waiter.done():
            self._waiter.set_result(self._timed_out)
        callbacks, self._on_finish = self._on_finish, []
        for callback in callbacks:
            callback()

    def when_finished(self, callback: Callable[[], object], /) -> None:
        """Run `callback` once when it stops; now if it already has."""
        if self._finished:
            callback()
        else:
            self._on_finish.append(callback)

    async def wait(self) -> bool:
        """Wait until it stops; returns whether it timed out."""
        if self._finished:
            return self._timed_out
        if self._waiter is None:
            self._waiter = asyncio.get_running_loop().create_future()
        return await self._waiter
