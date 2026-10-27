"""Run code at a time, after a delay, or on a cron schedule, without a sleeping task per job.

    @bot.scheduler.on("reminder")
    async def remind(job: Job) -> None:
        await bot.rest.messages.create(job.data["channel"], ...)

    await bot.scheduler.schedule("reminder", after=timedelta(hours=2), data={"channel": channel_id})
    await bot.scheduler.every("digest", "0 9 * * MON", tz="Europe/Paris")

One timer waits for the earliest job, however many there are, and wakes early when an earlier one is
added. Jobs live in a `JobStore`: in memory by default, or in Redis (`shoal.redis.RedisJobStore`),
where they survive restarts and every process of the bot shares them, each due job run by one.

A recurring job's next run is stored before it runs, so a crash mid-run does not lose the schedule.
A handler that raises is logged; the job is not retried.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import final
from zoneinfo import ZoneInfoNotFoundError

import msgspec

from shoal.core.clock import Clock, SystemClock, sleep_unless
from shoal.core.metrics import SCHEDULER_JOBS, Metrics, NoopMetrics
from shoal.core.tasks import cancel_and_wait, spawn
from shoal.tasks.cron import Cron
from shoal.tasks.defaults import (
    CLAIM_BATCH,
    CLOCK_SKEW_WAIT,
    IDLE_WAIT,
    MISFIRE_GRACE,
    SHARED_POLL,
    STORE_RETRY,
)
from shoal.tasks.jobs import Job, JobStore, JobStoreError, MemoryJobStore, Misfire

_log = logging.getLogger("shoal.tasks")

type JobHandler = Callable[[Job], Awaitable[None]]
"""Runs a job: `async def handler(job: Job) -> None`."""


@final
class Scheduler:
    """Runs jobs from a store when they come due.

    Args:
        store: Where jobs are kept. Defaults to a `MemoryJobStore`.
        clock: Time source.
        metrics: Receives `shoal_scheduler_jobs_total`.
    """

    __slots__ = ("_clock", "_closing", "_handlers", "_metrics", "_runner", "_running", "_store", "_wake")

    def __init__(
        self, store: JobStore | None = None, *, clock: Clock | None = None, metrics: Metrics | None = None
    ) -> None:
        """Create a stopped scheduler; see the class docstring for the arguments."""
        self._store: JobStore = store or MemoryJobStore()
        self._clock: Clock = clock or SystemClock()
        self._metrics: Metrics = metrics or NoopMetrics()
        self._handlers: dict[str, JobHandler] = {}
        self._runner: asyncio.Task[None] | None = None
        self._running: set[asyncio.Task[None]] = set()
        self._wake: asyncio.Event = asyncio.Event()
        """Set when a job is added or the scheduler closes: the timer re-reads the earliest job."""
        self._closing: bool = False

    @property
    def store(self) -> JobStore:
        """Where the jobs are kept."""
        return self._store

    def is_running(self) -> bool:
        """Whether the scheduler is started and not closed."""
        return self._runner is not None and not self._runner.done()

    def on(self, name: str) -> Callable[[JobHandler], JobHandler]:
        """Register the handler for jobs named `name` (one per name; a later one replaces it)."""

        def register(handler: JobHandler) -> JobHandler:
            self._handlers[name] = handler
            return handler

        return register

    async def schedule(
        self,
        name: str,
        *,
        at: datetime | None = None,
        after: timedelta | float | None = None,
        data: object = None,
        job_id: str | None = None,
        misfire: Misfire = Misfire.RUN,
    ) -> Job:
        """Run the `name` handler once, `at` a time or `after` a delay (seconds or a timedelta).

        Raises:
            ValueError: Neither or both of `at` and `after` given, or `at` is naive.
        """
        if (at is None) == (after is None):
            msg = "give exactly one of at and after"
            raise ValueError(msg)
        if at is not None:
            if at.tzinfo is None:
                msg = "at must be an aware datetime"
                raise ValueError(msg)
            due = at.timestamp()
        else:
            seconds = after.total_seconds() if isinstance(after, timedelta) else float(after or 0)
            due = self._clock.wall() + seconds
        job = Job(id=job_id or uuid.uuid4().hex, name=name, due=due, data=data, misfire=misfire)
        await self._add(job)
        return job

    async def every(
        self,
        name: str,
        cron: str,
        *,
        tz: str | None = None,
        data: object = None,
        job_id: str | None = None,
        misfire: Misfire = Misfire.RUN,
    ) -> Job:
        """Run the `name` handler on a cron schedule (`shoal.tasks.cron`), evaluated in `tz` (UTC).

        Give a `job_id` to schedule it at every start-up without adding a second copy: a stored job
        with that ID and the same schedule keeps its due time, so a run missed while the bot was
        down still follows its `misfire` policy.

        Raises:
            ValueError: The cron expression is not valid, or never fires.
            zoneinfo.ZoneInfoNotFoundError: `tz` names no known zone (on Windows, install `tzdata`).
        """
        now = datetime.fromtimestamp(self._clock.wall(), UTC)
        due = Cron.parse(cron, tz=tz).next_after(now).timestamp()
        existing = await self._store.get(job_id) if job_id is not None else None
        if existing is not None and (existing.cron, existing.tz) == (cron, tz):
            due = existing.due
        job = Job(
            id=job_id or uuid.uuid4().hex, name=name, due=due, data=data, cron=cron, tz=tz, misfire=misfire
        )
        await self._add(job)
        return job

    async def cancel(self, job_id: str) -> bool:
        """Cancel a job; whether it was scheduled."""
        return await self._store.cancel(job_id)

    async def get(self, job_id: str) -> Job | None:
        """A scheduled job."""
        return await self._store.get(job_id)

    async def jobs(self, name: str | None = None) -> list[Job]:
        """Every scheduled job, or those named `name`."""
        return await self._store.jobs(name)

    def start(self) -> None:
        """Start running due jobs. Starting a running scheduler does nothing.

        Raises:
            RuntimeError: The scheduler was closed.
        """
        if self._closing:
            msg = "the scheduler is closed"
            raise RuntimeError(msg)
        if not self.is_running():
            self._runner = spawn(self._run(), name="shoal-scheduler")

    async def close(self) -> None:
        """Stop the timer and wait for running handlers; cancelling `close` cancels them."""
        self._closing = True
        self._wake.set()
        if self._runner is not None:
            await cancel_and_wait(self._runner)
        running = set(self._running)
        if not running:
            return
        try:
            await asyncio.wait(running)
        except asyncio.CancelledError:
            for task in running:
                task.cancel()
            raise

    async def _add(self, job: Job) -> None:
        await self._store.add(job)
        self._wake.set()

    async def _run(self) -> None:
        while not self._closing:
            self._wake.clear()
            try:
                wait = await self._tick()
            except JobStoreError as error:
                # The store is unreachable (Redis down): keep the timer alive and look again.
                _log.warning("the job store failed; retrying in %.0f s: %r", STORE_RETRY, error)
                self._metrics.increment(SCHEDULER_JOBS, {"result": "store_error"})
                wait = STORE_RETRY
            except Exception:  # noqa: BLE001 - nothing one job holds may stop the timer for good
                _log.exception("the scheduler failed; retrying in %.0f s", STORE_RETRY)
                self._metrics.increment(SCHEDULER_JOBS, {"result": "store_error"})
                wait = STORE_RETRY
            await sleep_unless(self._clock, wait, self._wake)

    async def _tick(self) -> float:
        """Run what is due; how long to wait before looking again."""
        now = self._clock.wall()
        claimed = await self._store.claim(now, CLAIM_BATCH)
        for job in claimed:
            await self._dispatch(job, now)
        if len(claimed) == CLAIM_BATCH:
            return 0.0  # more are due: claim the next batch, letting others run first
        due = await self._store.next_due()
        wait = IDLE_WAIT if due is None else max(0.0, due - now)
        if not claimed and wait == 0:
            # Due by this host's clock but not by the store's (a shared store's clock is behind):
            # wait a little rather than ask again at once.
            wait = CLOCK_SKEW_WAIT
        if self._store.shared:
            wait = min(wait, SHARED_POLL)  # other processes add jobs without waking this one
        return wait

    async def _dispatch(self, job: Job, now: float) -> None:
        late = now - job.due > MISFIRE_GRACE
        if job.cron is not None:
            # Store the next run first: a crash in the handler must not end the schedule.
            moment = datetime.fromtimestamp(max(now, job.due), UTC)
            try:
                next_due = Cron.parse(job.cron, tz=job.tz).next_after(moment).timestamp()
            except (ValueError, ZoneInfoNotFoundError) as error:
                _log.warning("job %s (%s) has an unusable schedule; dropping it: %s", job.id, job.name, error)
                self._metrics.increment(SCHEDULER_JOBS, {"result": "dropped"})
                await self._store.done(job)
                return
            if not await self._store.reschedule(msgspec.structs.replace(job, due=next_due)):
                return  # cancelled since it was claimed
        if late and job.misfire is Misfire.SKIP:
            _log.info("skipping job %s (%s): it came due %.0f s ago", job.id, job.name, now - job.due)
            self._metrics.increment(SCHEDULER_JOBS, {"result": "skipped"})
            await self._store.done(job)
            return
        handler = self._handlers.get(job.name)
        if handler is None:
            _log.warning("no handler for job %s named %r; dropping it", job.id, job.name)
            self._metrics.increment(SCHEDULER_JOBS, {"result": "dropped"})
            await self._store.done(job)
            return
        task = spawn(self._call(handler, job), name=f"shoal-job-{job.name}")
        self._running.add(task)
        task.add_done_callback(self._running.discard)

    async def _call(self, handler: JobHandler, job: Job) -> None:
        try:
            await handler(job)
        except Exception:  # noqa: BLE001 - a failing job must not end the scheduler
            _log.exception("job %s (%s) raised", job.id, job.name)
            self._metrics.increment(SCHEDULER_JOBS, {"result": "failed"})
        else:
            self._metrics.increment(SCHEDULER_JOBS, {"result": "ran"})
        finally:
            await self._store.done(job)
