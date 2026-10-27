"""Background work: loops (`tasks.loop`), and jobs scheduled for a time or a cron schedule.

    from shoal import tasks

    @tasks.loop(minutes=5)
    async def refresh() -> None: ...

    await client.scheduler.schedule("reminder", after=timedelta(hours=2), data={"user": user_id})

`loop` runs in this process, for as long as it runs. The `Scheduler` keeps jobs in a store, so a
reminder set for next week survives restarts when the store is Redis (`shoal.redis.RedisJobStore`).
"""

from shoal.tasks import defaults
from shoal.tasks.cron import Cron
from shoal.tasks.jobs import Job, JobStore, JobStoreError, MemoryJobStore, Misfire
from shoal.tasks.loop import Loop, loop
from shoal.tasks.scheduler import JobHandler, Scheduler

__all__ = [
    "Cron",
    "Job",
    "JobHandler",
    "JobStore",
    "JobStoreError",
    "Loop",
    "MemoryJobStore",
    "Misfire",
    "Scheduler",
    "defaults",
    "loop",
]
