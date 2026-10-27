import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import override

import pytest

from shoal.core.metrics import SCHEDULER_JOBS, InMemoryMetrics
from shoal.tasks.defaults import CLOCK_SKEW_WAIT, MISFIRE_GRACE, SHARED_POLL, STORE_RETRY
from shoal.tasks.jobs import Job, JobStore, JobStoreError, MemoryJobStore, Misfire
from shoal.tasks.scheduler import Scheduler
from tests.support.fakes import ManualClock, settle


class Recorder:
    def __init__(self) -> None:
        self.ran: list[Job] = []

    async def __call__(self, job: Job) -> None:
        self.ran.append(job)


def started(store: JobStore | None = None) -> tuple[Scheduler, ManualClock, Recorder]:
    clock = ManualClock()
    scheduler = Scheduler(store, clock=clock)
    recorder = Recorder()
    _ = scheduler.on("reminder")(recorder)
    scheduler.start()
    return scheduler, clock, recorder


async def test_a_job_runs_once_after_its_delay_with_its_data() -> None:
    scheduler, clock, recorder = started()
    job = await scheduler.schedule("reminder", after=timedelta(minutes=5), data={"user": 1})
    await settle()
    await clock.advance(299)
    await settle()
    assert recorder.ran == []
    await clock.advance(1)
    await settle()
    assert [(ran.id, ran.data) for ran in recorder.ran] == [(job.id, {"user": 1})]
    assert await scheduler.jobs() == []
    await scheduler.close()


async def test_an_earlier_job_wakes_a_timer_waiting_for_a_later_one() -> None:
    scheduler, clock, recorder = started()
    _ = await scheduler.schedule("reminder", after=3600, job_id="late")
    await settle()
    soon = datetime.fromtimestamp(clock.wall() + 10, UTC)
    _ = await scheduler.schedule("reminder", at=soon, job_id="soon")
    await settle()
    await clock.advance(10)
    await settle()
    assert [ran.id for ran in recorder.ran] == ["soon"]
    assert await scheduler.cancel("late")
    assert await scheduler.get("late") is None
    await scheduler.close()
    assert not scheduler.is_running()


async def test_a_recurring_job_is_stored_again_before_it_runs(caplog: pytest.LogCaptureFixture) -> None:
    scheduler, clock, _ = started()
    calls: list[Job] = []

    @scheduler.on("digest")
    async def digest(job: Job) -> None:
        calls.append(job)
        raise RuntimeError

    job = await scheduler.every("digest", "*/15 * * * *", job_id="digest")
    assert job.due % 900 == 0
    assert 0 < job.due - clock.wall() <= 900
    await settle()
    await clock.advance(job.due - clock.wall())
    await settle()
    # It raised (logged), and is still scheduled for its next time.
    assert len(calls) == 1
    assert "job digest (digest) raised" in caplog.text
    stored = await scheduler.get("digest")
    assert stored is not None
    assert stored.due == job.due + 15 * 60
    await scheduler.close()


async def test_a_missed_job_runs_late_or_is_skipped_by_its_policy(caplog: pytest.LogCaptureFixture) -> None:
    store = MemoryJobStore()
    clock = ManualClock()
    long_ago = clock.wall() - MISFIRE_GRACE - 1
    await store.add(Job(id="run", name="reminder", due=long_ago))
    await store.add(Job(id="skip", name="reminder", due=long_ago, misfire=Misfire.SKIP))
    await store.add(Job(id="every", name="reminder", due=long_ago, cron="0 * * * *", misfire=Misfire.SKIP))
    scheduler = Scheduler(store, clock=clock)
    recorder = Recorder()
    _ = scheduler.on("reminder")(recorder)
    with caplog.at_level(logging.INFO, logger="shoal.tasks"):
        scheduler.start()
        await settle()
    assert [ran.id for ran in recorder.ran] == ["run"]
    assert "skipping job skip" in caplog.text
    # The skipped recurring job waits for its next time.
    every = await store.get("every")
    assert every is not None
    assert every.due > clock.wall()
    await scheduler.close()


async def test_jobs_without_a_handler_or_with_a_bad_schedule_are_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = MemoryJobStore()
    clock = ManualClock()
    await store.add(Job(id="orphan", name="nobody", due=clock.wall()))
    await store.add(Job(id="bad", name="reminder", due=clock.wall(), cron="0 0 30 2 *"))
    scheduler = Scheduler(store, clock=clock)
    scheduler.start()
    await settle()
    assert "no handler for job orphan" in caplog.text
    assert "job bad (reminder) has an unusable schedule" in caplog.text
    assert await store.jobs() == []
    await scheduler.close()


async def test_more_due_jobs_than_a_batch_all_run() -> None:
    scheduler, clock, recorder = started()
    for number in range(250):
        _ = await scheduler.schedule("reminder", after=1, job_id=str(number))
    await clock.advance(1)
    await settle(200)
    assert len(recorder.ran) == 250
    await scheduler.close()


class FailingStore(JobStore):
    """A shared store whose first claim fails, as Redis does while unreachable."""

    def __init__(self) -> None:
        self.inner = MemoryJobStore()
        self.failures = 1

    @property
    @override
    def shared(self) -> bool:
        return True

    @override
    async def add(self, job: Job) -> None:
        await self.inner.add(job)

    @override
    async def cancel(self, job_id: str) -> bool:
        return await self.inner.cancel(job_id)

    @override
    async def get(self, job_id: str) -> Job | None:
        return await self.inner.get(job_id)

    @override
    async def jobs(self, name: str | None = None) -> list[Job]:
        return await self.inner.jobs(name)

    @override
    async def next_due(self) -> float | None:
        return await self.inner.next_due()

    @override
    async def claim(self, now: float, limit: int) -> list[Job]:
        if self.failures:
            self.failures -= 1
            msg = "connection refused"
            raise JobStoreError(msg)
        return await self.inner.claim(now, limit)

    @override
    async def reschedule(self, job: Job) -> bool:
        return await self.inner.reschedule(job)

    @override
    async def done(self, job: Job) -> None:
        await self.inner.done(job)


async def test_a_failing_store_is_retried_and_a_shared_one_polled(caplog: pytest.LogCaptureFixture) -> None:
    store = FailingStore()
    clock = ManualClock()
    await store.add(Job(id="a", name="reminder", due=clock.wall() + 3600))
    scheduler = Scheduler(store, clock=clock)
    recorder = Recorder()
    _ = scheduler.on("reminder")(recorder)
    scheduler.start()
    await settle()
    assert "the job store failed" in caplog.text
    await clock.advance(STORE_RETRY)
    await settle()
    # Another process adds a job due now: this one sees it within a poll, without being woken.
    await store.add(Job(id="b", name="reminder", due=clock.wall()))
    await clock.advance(SHARED_POLL)
    await settle()
    assert [ran.id for ran in recorder.ran] == ["b"]
    await scheduler.close()


async def test_scheduling_needs_exactly_one_time() -> None:
    scheduler = Scheduler(clock=ManualClock())
    with pytest.raises(ValueError, match="exactly one"):
        _ = await scheduler.schedule("reminder")
    with pytest.raises(ValueError, match="exactly one"):
        _ = await scheduler.schedule("reminder", at=datetime.now(UTC), after=1)
    with pytest.raises(ValueError, match="aware"):
        _ = await scheduler.schedule("reminder", at=datetime(2026, 1, 1))  # noqa: DTZ001 - the case under test
    with pytest.raises(ValueError, match="five fields"):
        _ = await scheduler.every("digest", "* *")
    assert isinstance(scheduler.store, MemoryJobStore)


async def test_closing_waits_for_running_jobs_and_a_closed_scheduler_cannot_start() -> None:
    scheduler, clock, _ = started()
    finished: list[str] = []

    @scheduler.on("slow")
    async def slow(job: Job) -> None:
        await clock.sleep(10)
        finished.append(job.id)

    _ = await scheduler.schedule("slow", after=0, job_id="slow")
    await settle()
    scheduler.start()  # already running: nothing happens
    closing = asyncio.ensure_future(scheduler.close())
    await settle()
    assert not closing.done()
    await clock.advance(10)
    await closing
    assert finished == ["slow"]
    with pytest.raises(RuntimeError, match="closed"):
        scheduler.start()


async def test_every_at_start_up_keeps_a_missed_run_and_counts_results() -> None:
    store = MemoryJobStore()
    clock = ManualClock()
    metrics = InMemoryMetrics()
    missed = clock.wall() - 10
    await store.add(Job(id="digest", name="reminder", due=missed, cron="0 * * * *"))
    scheduler = Scheduler(store, clock=clock, metrics=metrics)
    recorder = Recorder()
    _ = scheduler.on("reminder")(recorder)
    kept = await scheduler.every("reminder", "0 * * * *", job_id="digest")
    assert kept.due == missed
    scheduler.start()
    await settle()
    assert [ran.id for ran in recorder.ran] == ["digest"]
    assert metrics.counters[InMemoryMetrics.key(SCHEDULER_JOBS, {"result": "ran"})] == 1
    # A changed schedule is a new one: it takes its own next time.
    changed = await scheduler.every("reminder", "30 * * * *", job_id="digest")
    assert changed.due > clock.wall()
    await scheduler.close()


async def test_a_job_cancelled_while_it_runs_stays_cancelled() -> None:
    scheduler, clock, _ = started()
    release = asyncio.Event()

    @scheduler.on("digest")
    async def digest(_job: Job) -> None:
        await release.wait()

    job = await scheduler.every("digest", "* * * * *", job_id="digest")
    await clock.advance(job.due - clock.wall())
    await settle()
    assert await scheduler.cancel("digest")
    release.set()
    await settle()
    assert await scheduler.get("digest") is None
    await scheduler.close()


async def test_any_error_in_the_timer_is_retried(caplog: pytest.LogCaptureFixture) -> None:
    class Broken(FailingStore):
        """Raises something that is not a store error once, as a bug in a custom store would."""

        broken = True

        @override
        async def next_due(self) -> float | None:
            if Broken.broken:
                Broken.broken = False
                raise OverflowError
            return await self.inner.next_due()

    clock = ManualClock()
    broken = Broken()
    broken.failures = 0
    scheduler = Scheduler(broken, clock=clock)
    recorder = Recorder()
    _ = scheduler.on("reminder")(recorder)
    scheduler.start()
    await settle()
    assert "the scheduler failed" in caplog.text
    _ = await scheduler.schedule("reminder", after=0)
    await settle()
    assert len(recorder.ran) == 1
    await scheduler.close()


async def test_a_store_clock_behind_this_host_does_not_spin() -> None:
    class Behind(FailingStore):
        """Says a job is next due but releases nothing yet, as a store whose clock is behind."""

        claims = 0

        @override
        async def claim(self, now: float, limit: int) -> list[Job]:
            Behind.claims += 1
            return []

    store = Behind()
    store.failures = 0
    clock = ManualClock()
    await store.add(Job(id="a", name="reminder", due=clock.wall()))
    scheduler = Scheduler(store, clock=clock)
    scheduler.start()
    await settle(50)
    assert Behind.claims == 1
    await clock.advance(CLOCK_SKEW_WAIT)
    await settle(50)
    assert Behind.claims == 2
    await scheduler.close()


async def test_cancelling_close_cancels_running_jobs() -> None:
    scheduler, clock, _ = started()
    cancelled = asyncio.Event()

    @scheduler.on("slow")
    async def slow(_job: Job) -> None:
        try:
            await clock.sleep(100)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    _ = await scheduler.schedule("slow", after=0)
    await settle()
    closing = asyncio.ensure_future(scheduler.close())
    await settle()
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    await settle()
    assert cancelled.is_set()
