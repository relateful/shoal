"""Scheduled jobs and where they are kept.

A job is a name (which handler runs it), a due time, and data for the handler. `MemoryJobStore`
keeps jobs in this process; `shoal.redis.RedisJobStore` keeps them in Redis, where they survive
restarts and each due job is claimed by exactly one process.
"""

import heapq
import itertools
from enum import StrEnum
from typing import Protocol, final, override

import msgspec

from shoal.core.errors import ShoalError


class JobStoreError(ShoalError):
    """The job store could not be reached or answered with something unreadable.

    The scheduler logs it and tries again after `STORE_RETRY` seconds.
    """


class Misfire(StrEnum):
    """What a job does when it comes due while nothing was running to run it (the bot was down)."""

    RUN = "run"
    """Run once as soon as possible; a recurring job then carries on from now."""
    SKIP = "skip"
    """Do not run late: a one-off job is dropped, a recurring one waits for its next time."""


class Job(msgspec.Struct, frozen=True, kw_only=True):
    """One scheduled job.

    Attributes:
        id: Unique within the store; scheduling a job with an existing ID replaces it.
        name: The handler that runs it (`Scheduler.on`).
        due: When it runs, in Unix seconds.
        data: What the handler is given: anything msgspec encodes (dicts, lists, strings, numbers).
        cron: For a recurring job, its cron expression (`shoal.tasks.cron`).
        tz: The time zone `cron` is evaluated in; `None` is UTC.
        misfire: What happens when it comes due while nothing could run it.
    """

    id: str
    name: str
    due: float
    data: object = None
    cron: str | None = None
    tz: str | None = None
    misfire: Misfire = Misfire.RUN


class JobStore(Protocol):
    """Where a scheduler keeps its jobs. Every method raises `JobStoreError` when the store fails."""

    __slots__ = ()

    @property
    def shared(self) -> bool:
        """Whether other processes add and claim jobs here too (the scheduler then polls)."""
        ...

    async def add(self, job: Job) -> None:
        """Store a job, replacing any with its ID."""
        ...

    async def cancel(self, job_id: str) -> bool:
        """Remove a job; whether it existed."""
        ...

    async def get(self, job_id: str) -> Job | None:
        """A stored job."""
        ...

    async def jobs(self, name: str | None = None) -> list[Job]:
        """Every stored job, or those with `name`."""
        ...

    async def next_due(self) -> float | None:
        """When the earliest job is due, or `None` with no jobs."""
        ...

    async def claim(self, now: float, limit: int) -> list[Job]:
        """Take up to `limit` jobs due by `now`, earliest first; no other claim gets them.

        A shared store compares due times with its own clock instead of `now`. A job claimed again
        after the process running it died comes back with `due` set to now, so it is not taken
        for missed.
        """
        ...

    async def reschedule(self, job: Job) -> bool:
        """Store a claimed job's next run, unless it was cancelled meanwhile; whether it was stored."""
        ...

    async def done(self, job: Job) -> None:
        """A claimed job finished; forget it unless it was scheduled again meanwhile."""
        ...


@final
class MemoryJobStore(JobStore):
    """Jobs kept in this process: lost on restart, for one-process bots and tests.

    A heap orders jobs by due time, so finding and claiming the next one costs O(log n) however many
    are waiting.
    """

    __slots__ = ("_claimed", "_heap", "_jobs", "_order")

    def __init__(self) -> None:
        """Create an empty store."""
        self._jobs: dict[str, Job] = {}
        self._heap: list[tuple[float, int, str]] = []
        """(due, insertion order, ID); entries whose job was replaced or cancelled are skipped."""
        self._order: itertools.count[int] = itertools.count()
        self._claimed: set[str] = set()
        """Claimed jobs not done yet: `reschedule` stores only these, `cancel` forgets them."""

    @property
    @override
    def shared(self) -> bool:
        return False

    @override
    async def add(self, job: Job) -> None:
        self._jobs[job.id] = job
        heapq.heappush(self._heap, (job.due, next(self._order), job.id))

    @override
    async def cancel(self, job_id: str) -> bool:
        claimed = job_id in self._claimed
        self._claimed.discard(job_id)
        return self._jobs.pop(job_id, None) is not None or claimed

    @override
    async def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    @override
    async def jobs(self, name: str | None = None) -> list[Job]:
        return [job for job in self._jobs.values() if name is None or job.name == name]

    @override
    async def next_due(self) -> float | None:
        self._drop_outdated()
        return self._heap[0][0] if self._heap else None

    @override
    async def claim(self, now: float, limit: int) -> list[Job]:
        claimed: list[Job] = []
        while len(claimed) < limit:
            self._drop_outdated()
            if not self._heap or self._heap[0][0] > now:
                break
            _, _, job_id = heapq.heappop(self._heap)
            claimed.append(self._jobs.pop(job_id))
            self._claimed.add(job_id)
        return claimed

    @override
    async def reschedule(self, job: Job) -> bool:
        if job.id not in self._claimed:
            return False
        await self.add(job)
        return True

    @override
    async def done(self, job: Job) -> None:
        self._claimed.discard(job.id)

    def _drop_outdated(self) -> None:
        """Pop heap entries for jobs cancelled or replaced since they were pushed."""
        while self._heap:
            due, _, job_id = self._heap[0]
            job = self._jobs.get(job_id)
            if job is not None and job.due == due:
                return
            heapq.heappop(self._heap)
