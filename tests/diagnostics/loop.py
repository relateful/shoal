import asyncio
import logging
import threading
import time
from collections.abc import Mapping
from typing import override

import pytest

from shoal.core.metrics import LOOP_BLOCK_SECONDS, LOOP_BLOCKS, InMemoryMetrics, Metrics, MetricSpec
from shoal.diagnostics.loop import BlockReport, LoopMonitor


def is_running(monitor: LoopMonitor) -> bool:
    """Read through a call so type checkers do not narrow the property across awaits."""
    return monitor.running


def block_the_loop_for(seconds: float) -> None:
    time.sleep(seconds)


async def test_a_blocking_call_is_reported_with_its_location(caplog: pytest.LogCaptureFixture) -> None:
    reports: list[BlockReport] = []
    reported = threading.Event()

    def on_block(report: BlockReport) -> None:
        reports.append(report)
        reported.set()

    metrics = InMemoryMetrics()
    with caplog.at_level(logging.WARNING, logger="shoal.diagnostics.loop"):
        async with LoopMonitor(threshold=0.1, interval=0.02, metrics=metrics, on_block=on_block) as monitor:
            assert is_running(monitor)
            await asyncio.sleep(0.05)
            block_the_loop_for(0.5)
            await asyncio.sleep(0.2)
        assert not is_running(monitor)

    assert reported.is_set()
    [report] = reports
    assert report.blocked_for >= 0.1
    assert report.culprit is not None
    assert "loop.py" in report.culprit
    assert "block_the_loop_for" in report.culprit
    assert "time.sleep" in report.stack or "block_the_loop_for" in report.stack
    assert "likely culprit" in caplog.text
    assert "recovered after being blocked" in caplog.text
    assert metrics.counters[InMemoryMetrics.key(LOOP_BLOCKS)] == 1
    assert metrics.observations[InMemoryMetrics.key(LOOP_BLOCK_SECONDS)][0] >= 0.3


async def test_a_healthy_loop_reports_nothing() -> None:
    reports: list[BlockReport] = []
    async with LoopMonitor(threshold=0.2, interval=0.02, on_block=reports.append):
        for _ in range(10):
            await asyncio.sleep(0.02)
    assert reports == []


async def test_a_failing_callback_does_not_stop_the_watchdog(caplog: pytest.LogCaptureFixture) -> None:
    def explode(report: BlockReport) -> None:
        raise RuntimeError(report.culprit)

    monitor = LoopMonitor(threshold=0.1, interval=0.02, on_block=explode)
    with caplog.at_level(logging.ERROR, logger="shoal.diagnostics.loop"):
        await monitor.start()
        await monitor.start()
        await asyncio.sleep(0.05)
        block_the_loop_for(0.3)
        await asyncio.sleep(0.1)
        await monitor.stop()
        await monitor.stop()
    assert "on_block callback failed" in caplog.text


def test_threshold_must_exceed_interval() -> None:
    with pytest.raises(ValueError, match="threshold"):
        LoopMonitor(threshold=0.05, interval=0.05)


async def test_a_failing_metrics_backend_does_not_stop_the_ticks(caplog: pytest.LogCaptureFixture) -> None:
    class BrokenMetrics(Metrics):
        @override
        def increment(
            self, spec: MetricSpec, labels: Mapping[str, str] | None = None, value: float = 1.0
        ) -> None:
            pass

        @override
        def set(self, spec: MetricSpec, value: float, labels: Mapping[str, str] | None = None) -> None:
            msg = "backend down"
            raise RuntimeError(msg)

        @override
        def observe(self, spec: MetricSpec, value: float, labels: Mapping[str, str] | None = None) -> None:
            pass

    monitor = LoopMonitor(threshold=0.5, interval=0.02, metrics=BrokenMetrics())
    with caplog.at_level(logging.ERROR, logger="shoal.diagnostics"):
        async with monitor:
            await asyncio.sleep(0.1)
            assert monitor.check(time.monotonic()) is None
    assert "could not record loop lag" in caplog.text
    assert not is_running(monitor)


def test_the_watchdog_ends_when_its_loop_is_closed() -> None:
    monitor = LoopMonitor(threshold=0.5, interval=0.01)

    async def start_and_never_stop() -> None:
        await monitor.start()

    asyncio.run(start_and_never_stop())
    watchdogs = [thread for thread in threading.enumerate() if thread.name == "shoal-loop-watchdog"]
    for watchdog in watchdogs:
        watchdog.join(timeout=5)
    assert not any(watchdog.is_alive() for watchdog in watchdogs)
