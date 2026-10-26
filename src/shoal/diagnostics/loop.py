"""Detects a blocked event loop and reports the code that is blocking it.

A Discord bot runs on one asyncio event loop. A single blocking call (`requests.get`, `time.sleep`, a
slow database driver, heavy CPU work) freezes everything: heartbeats are late, Discord drops the
connection, events pile up, and the logs only show the consequences.

`LoopMonitor` runs a tiny task on the loop that ticks every `interval`, and a watchdog thread that
watches the ticks. When the ticks stop for longer than `threshold`, the watchdog captures the event
loop thread's stack *while it is blocked* and logs it, naming the first frame in your code. When the
loop recovers it logs how long the block lasted.

    async with LoopMonitor(threshold=0.25):
        await bot.run()
"""

import asyncio
import logging
import sys
import sysconfig
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import FrameType, TracebackType
from typing import Final, Self, final

from shoal.core.metrics import LOOP_BLOCK_SECONDS, LOOP_BLOCKS, LOOP_LAG_SECONDS, Metrics, NoopMetrics
from shoal.core.tasks import cancel_and_wait
from shoal.diagnostics.defaults import LOOP_BLOCK_THRESHOLD, LOOP_CHECK_INTERVAL

_log = logging.getLogger("shoal.diagnostics.loop")

_LIBRARY_ROOTS: Final = tuple(
    str(Path(path).resolve())
    for key in ("stdlib", "platstdlib", "purelib", "platlib")
    if (path := sysconfig.get_paths().get(key))
)


@dataclass(frozen=True, slots=True)
class BlockReport:
    """A detected block of the event loop."""

    blocked_for: float
    """Seconds the loop had been blocked when the stack was captured."""
    stack: str
    """The event loop thread's stack at that moment, formatted like a traceback."""
    culprit: str | None
    """`file:line in function` of the innermost frame outside the standard library and installed
    packages, which is usually the blocking call in your code. `None` if every frame was library code.
    """


def _culprit(frame: FrameType | None) -> str | None:
    while frame is not None:
        filename = str(Path(frame.f_code.co_filename).resolve())
        if not filename.startswith(_LIBRARY_ROOTS):
            return f"{frame.f_code.co_filename}:{frame.f_lineno} in {frame.f_code.co_name}"
        frame = frame.f_back
    return None


def _thread_frame(thread_id: int) -> FrameType | None:
    frames: dict[int, FrameType] = sys._current_frames()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage] - documented CPython API for sampling another thread's stack
    return frames.get(thread_id)


@final
class LoopMonitor:
    """Watches the running event loop for blocking calls.

    Args:
        threshold: Seconds without a tick before a block is reported.
        interval: Seconds between ticks (and watchdog checks).
        metrics: Receives `shoal_loop_lag_seconds`, `shoal_loop_blocks_total` and
            `shoal_loop_block_seconds`.
        on_block: Called (from the watchdog thread) with each report, in addition to logging. Keep it
            fast and thread-safe; use `loop.call_soon_threadsafe` to get back onto the loop.
    """

    __slots__ = (
        "_blocked_since",
        "_interval",
        "_last_tick",
        "_loop_thread",
        "_metrics",
        "_on_block",
        "_stop",
        "_threshold",
        "_ticker",
        "_watchdog",
    )

    def __init__(
        self,
        *,
        threshold: float = LOOP_BLOCK_THRESHOLD,
        interval: float = LOOP_CHECK_INTERVAL,
        metrics: Metrics | None = None,
        on_block: Callable[[BlockReport], None] | None = None,
    ) -> None:
        """Create a monitor; see the class docstring for the arguments."""
        if threshold <= interval:
            msg = "threshold must be larger than interval"
            raise ValueError(msg)
        self._threshold: float = threshold
        self._interval: float = interval
        self._metrics: Metrics = metrics or NoopMetrics()
        self._on_block: Callable[[BlockReport], None] | None = on_block
        self._last_tick: float = time.monotonic()
        self._blocked_since: float | None = None
        self._loop_thread: int | None = None
        self._ticker: asyncio.Task[None] | None = None
        self._watchdog: threading.Thread | None = None
        self._stop: threading.Event = threading.Event()

    @property
    def running(self) -> bool:
        """Whether the monitor is watching a loop."""
        return self._ticker is not None

    async def start(self) -> None:
        """Start watching the running loop. Idempotent."""
        if self._ticker is not None:
            return
        self._loop_thread = threading.get_ident()
        self._last_tick = time.monotonic()
        self._blocked_since = None
        # A fresh event per run: a watchdog still finishing from an earlier `stop` keeps its own.
        self._stop = threading.Event()
        self._ticker = asyncio.create_task(self._tick(), name="shoal-loop-monitor")
        loop = asyncio.get_running_loop()
        self._watchdog = threading.Thread(
            target=self._watch, args=(loop,), name="shoal-loop-watchdog", daemon=True
        )
        self._watchdog.start()

    async def stop(self) -> None:
        """Stop watching. Idempotent."""
        self._stop.set()
        ticker, self._ticker = self._ticker, None
        watchdog, self._watchdog = self._watchdog, None
        if ticker is not None:
            error = await cancel_and_wait(ticker)
            if error is not None:
                _log.error("LoopMonitor ticker had failed: %r", error)
        if watchdog is not None:
            await asyncio.to_thread(watchdog.join)

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.stop()

    async def _tick(self) -> None:
        while True:
            before = time.monotonic()
            await asyncio.sleep(self._interval)
            now = time.monotonic()
            self._last_tick = now
            try:
                self._metrics.set(LOOP_LAG_SECONDS, max(0.0, now - before - self._interval))
            except Exception:  # noqa: BLE001 - a broken metrics backend must not stop the ticks
                _log.exception("LoopMonitor could not record loop lag")

    def _watch(self, loop: asyncio.AbstractEventLoop) -> None:
        stop = self._stop
        while not stop.wait(self._interval):
            if loop.is_closed():
                # The loop ended without `stop`; nothing is left to watch.
                return
            if loop.is_running():
                try:
                    self.check(time.monotonic())
                except Exception:  # noqa: BLE001 - a broken metrics backend must not end the watchdog
                    _log.exception("LoopMonitor check failed")

    def check(self, now: float) -> BlockReport | None:
        """Compare the last tick with `now`, reporting a new block or the end of one.

        Called by the watchdog thread; public so the detection logic can be tested directly.
        """
        last_tick = self._last_tick  # read once: the loop thread may tick meanwhile
        silent_for = now - last_tick
        if silent_for <= self._threshold:
            if self._blocked_since is not None:
                duration = last_tick - self._blocked_since
                self._blocked_since = None
                self._metrics.observe(LOOP_BLOCK_SECONDS, duration)
                _log.warning("event loop recovered after being blocked for %.3fs", duration)
            return None
        if self._blocked_since is not None:
            return None
        self._blocked_since = last_tick
        frame = _thread_frame(self._loop_thread) if self._loop_thread is not None else None
        report = BlockReport(
            blocked_for=silent_for,
            stack="".join(traceback.format_stack(frame)) if frame is not None else "",
            culprit=_culprit(frame),
        )
        self._metrics.increment(LOOP_BLOCKS)
        _log.warning(
            "event loop blocked for %.3fs so far; likely culprit: %s\n%s",
            silent_for,
            report.culprit or "unknown (only library frames on the stack)",
            report.stack,
        )
        if self._on_block is not None:
            try:
                self._on_block(report)
            except Exception:  # noqa: BLE001 - a broken callback must not kill the watchdog
                _log.exception("LoopMonitor on_block callback failed")
        return report
