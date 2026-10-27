# Loops and scheduled jobs

Shoal has two ways to run code later, for two kinds of work:

- **`tasks.loop`** repeats a function in this process: refresh a status every five minutes, post at
  09:00 each day. It stops when the process stops.
- **`client.scheduler`** runs a job at a time, after a delay, or on a cron schedule, from a store.
  With Redis, a reminder set for next week survives restarts and deploys, and only one of the
  bot's processes runs it each time it comes due ([surviving restarts](#surviving-restarts)).

## Loops

```python
import datetime as dt

from shoal import commands, tasks


class Status(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @tasks.loop(minutes=5)
    async def refresh(self) -> None:
        ...

    @refresh.before_loop
    async def before(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(time=dt.time(9, 0, tzinfo=dt.timezone.utc))
    async def morning(self) -> None:
        ...

    async def cog_load(self) -> None:
        self.refresh.start()
        self.morning.start()

    async def cog_unload(self) -> None:
        self.refresh.cancel()
        self.morning.cancel()
```

A loop takes `seconds`, `minutes`, `hours`, `time` (one or several times
of day; naive times are UTC), `count`, then `start`, `stop` (after the current iteration), `cancel`,
`restart`, `is_running`, `current_loop`, `next_iteration`, `change_interval`, and the `before_loop`,
`after_loop` and `error` hooks. Each instance of a class gets its own loop, so the class needs a
`__dict__` (any ordinary class has one).

Iterations keep to an absolute schedule: with `minutes=5`, the loop runs at start, start + 5,
start + 10, and so on, however long each iteration takes. An iteration that runs past its next slot
does not cause a burst of catch-up runs; the loop carries on at the next slot. An iteration that
raises ends the loop: the `error` hook gets the exception, or it is logged.

## Scheduled jobs

```python
from datetime import timedelta

import msgspec

import shoal
from shoal.tasks import Job


class Reminder(msgspec.Struct):
    channel: int
    user: int
    text: str


@bot.scheduler.on("reminder")
async def remind(job: Job) -> None:
    data = msgspec.convert(job.data, Reminder)
    channel = bot.get_channel(data.channel)
    if channel is not None:
        await channel.send(f"<@{data.user}>, {data.text}")


@bot.tree.command()
async def remindme(interaction: shoal.Interaction, minutes: int, text: str) -> None:
    await bot.scheduler.schedule(
        "reminder",
        after=timedelta(minutes=minutes),
        data={"channel": interaction.channel_id, "user": interaction.user.id, "text": text},
    )
    await interaction.response.send_message("I'll remind you.", ephemeral=True)
```

- `schedule(name, at=..., after=..., data=...)` runs the `name` handler once, at an aware
  `datetime` or after a delay. `data` is anything msgspec encodes.
- `every(name, "0 9 * * MON", tz="Europe/Paris", job_id="digest")` runs it on a cron schedule:
  minute, hour, day of month, month, day of week, with `*`, ranges, lists, steps and names. Give
  a `job_id` when scheduling at every start-up, so the job is not duplicated; a stored job with
  the same schedule keeps its due time, so a run missed while the bot was down still runs. Time
  zone names need the `tzdata` package on Windows (`pip install tzdata`).
- `cancel(job_id)`, `get(job_id)` and `jobs(name)` manage what is scheduled.

The scheduler starts after `setup_hook` and stops on `close`, waiting for running jobs. One timer
waits for the earliest job, however many there are, and an earlier job added meanwhile wakes it. A
recurring job's next run is stored before it runs, so a failing handler (logged) keeps its
schedule. Jobs are not retried.

### Missed jobs

A job that comes due while the bot is down runs as soon as the scheduler starts. With
`misfire=Misfire.SKIP`, a job more than a minute late does not run: a one-off job is dropped, and a
recurring one waits for its next time. A recurring job that missed several times runs once, then
carries on from now.

### Surviving restarts

```python
from redis.asyncio import Redis
from shoal.redis import RedisJobStore

bot = commands.Bot(..., job_store=RedisJobStore(Redis.from_url("redis://localhost")))
```

The default store keeps jobs in memory, so they are lost on restart. `RedisJobStore` keeps them in
Redis. A due job is claimed by one process, which holds a five-minute lease on it until the handler
finishes. If that process dies mid-job, the lease runs out and another process runs the job again.
A job retried this way runs as due now, not as missed. Jobs therefore run **at least once**: a handler that must not repeat its work should check whether
it is already done. Processes sharing a store look for new jobs every five seconds, so a job added
by another process starts at most that late. While Redis is unreachable the scheduler logs it and
tries again every five seconds.
