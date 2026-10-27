"""Scheduled jobs shared by every process of a bot, in Redis.

    scheduler = Scheduler(RedisJobStore(redis))

Jobs survive restarts and deploys. A due job is claimed by one process in a script, which leases it
for `lease` seconds; finishing it ends the lease. A process that dies mid-job leaves the lease to
expire, and the job is claimed again: jobs run at least once, so a handler that must not repeat
(a payment, a message) should check whether its work is already done.

Keys: `jobs:due` (sorted set of IDs by due time, ms), `jobs:leased` (IDs by lease expiry, ms),
`jobs:retried` (IDs requeued after a lease ran out) and `jobs:data` (hash of ID to the job,
msgpack). Claims compare with Redis's clock, as every script does, so hosts' clocks only set the
due times they ask for.
"""

import logging
from typing import Final, cast, final, override

import msgspec
from redis.exceptions import RedisError

from shoal.redis.base import NOW_MS, Redis, key_of, text_of
from shoal.redis.defaults import JOB_LEASE, KEY_PREFIX
from shoal.tasks.jobs import Job, JobStore, JobStoreError

_log = logging.getLogger("shoal.redis")

_ADD: Final = """
redis.call('HSET', KEYS[4], ARGV[1], ARGV[3])
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[1])
"""
"""Store a job and its due time together."""

_RESCHEDULE: Final = """
if redis.call('HEXISTS', KEYS[4], ARGV[1]) == 0 then
  return 0
end
redis.call('HSET', KEYS[4], ARGV[1], ARGV[3])
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[1])
return 1
"""
"""Store a claimed job's next run, unless it was cancelled meanwhile (its data is gone)."""

_CANCEL: Final = """
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('ZREM', KEYS[2], ARGV[1])
redis.call('SREM', KEYS[3], ARGV[1])
return redis.call('HDEL', KEYS[4], ARGV[1])
"""
"""Forget a job wherever it is; 1 if it existed."""

_CLAIM: Final = (
    NOW_MS
    + """
local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', now)
for _, id in ipairs(expired) do
  redis.call('ZREM', KEYS[2], id)
  if redis.call('ZSCORE', KEYS[1], id) == false and redis.call('HEXISTS', KEYS[4], id) == 1 then
    redis.call('ZADD', KEYS[1], 0, id)
    redis.call('SADD', KEYS[3], id)
  end
end
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', now, 'LIMIT', 0, tonumber(ARGV[1]))
local claimed = {}
for _, id in ipairs(due) do
  redis.call('ZREM', KEYS[1], id)
  local retried = redis.call('SREM', KEYS[3], id)
  local data = redis.call('HGET', KEYS[4], id)
  if data then
    redis.call('ZADD', KEYS[2], now + tonumber(ARGV[2]), id)
    claimed[#claimed + 1] = id
    claimed[#claimed + 1] = data
    claimed[#claimed + 1] = retried
  end
end
return claimed
"""
)
"""Requeue jobs whose lease expired (their process died), then lease up to ARGV[1] due by Redis's
clock. Returns ID, data, retried (1 or 0) for each."""

_DONE: Final = """
redis.call('ZREM', KEYS[2], ARGV[1])
if redis.call('ZSCORE', KEYS[1], ARGV[1]) == false then
  redis.call('HDEL', KEYS[4], ARGV[1])
end
"""
"""End a job's lease; forget it unless it was scheduled again (a recurring job's next run)."""

_NEXT: Final = """
local due = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
local leased = redis.call('ZRANGE', KEYS[2], 0, 0, 'WITHSCORES')
local first = due[2] and tonumber(due[2])
if leased[2] and (first == nil or tonumber(leased[2]) < first) then
  first = tonumber(leased[2])
end
return first and tostring(first)
"""
"""The earliest due time or lease expiry (ms, as text), or nil."""

_CLAIM_FIELDS: Final = 3
"""ID, data and the retried flag, per claimed job."""

_ENCODER: Final = msgspec.msgpack.Encoder()
_DECODER: Final = msgspec.msgpack.Decoder(Job)


@final
class RedisJobStore(JobStore):
    """Jobs in Redis, claimed by one process at a time.

    Args:
        redis: The client.
        prefix: What the keys start with; give each bot its own.
        lease: Seconds a claimed job is held before another process may run it again. Longer than
            any handler takes.
    """

    __slots__ = ("_keys", "_lease_ms", "_redis")

    def __init__(self, redis: Redis, *, prefix: str = KEY_PREFIX, lease: float = JOB_LEASE) -> None:
        """Create a store; see the class docstring for the arguments."""
        self._redis: Redis = redis
        self._keys: tuple[str, str, str, str] = (
            key_of(prefix, "jobs", "due"),
            key_of(prefix, "jobs", "leased"),
            key_of(prefix, "jobs", "retried"),
            key_of(prefix, "jobs", "data"),
        )
        self._lease_ms: int = round(lease * 1000)

    @property
    @override
    def shared(self) -> bool:
        return True

    @override
    async def add(self, job: Job) -> None:
        await self._eval(_ADD, job.id, str(round(job.due * 1000)), _ENCODER.encode(job))

    @override
    async def reschedule(self, job: Job) -> bool:
        return await self._eval(_RESCHEDULE, job.id, str(round(job.due * 1000)), _ENCODER.encode(job)) == 1

    @override
    async def cancel(self, job_id: str) -> bool:
        return await self._eval(_CANCEL, job_id) == 1

    @override
    async def get(self, job_id: str) -> Job | None:
        try:
            data = await self._redis.hget(self._keys[3], job_id)
        except RedisError as error:
            raise JobStoreError(str(error)) from error
        return None if data is None else _decode(data)

    @override
    async def jobs(self, name: str | None = None) -> list[Job]:
        try:
            values = await self._redis.hvals(self._keys[3])
        except RedisError as error:
            raise JobStoreError(str(error)) from error
        decoded = [job for value in values if (job := _readable(value)) is not None]
        return [job for job in decoded if name is None or job.name == name]

    @override
    async def next_due(self) -> float | None:
        answer = await self._eval(_NEXT)
        return None if answer is None else float(text_of(_text(answer))) / 1000

    @override
    async def claim(self, now: float, limit: int) -> list[Job]:
        answer = await self._eval(_CLAIM, str(limit), str(self._lease_ms))
        if not isinstance(answer, list):
            msg = f"Redis answered a job claim with {answer!r}"
            raise JobStoreError(msg)
        rows = cast("list[object]", answer)  # a Lua table: redis-py does not type it
        claimed: list[Job] = []
        for index in range(0, len(rows), _CLAIM_FIELDS):
            job_id, data, retried = rows[index : index + _CLAIM_FIELDS]
            job = _readable(_text(data))
            if job is None:
                # Unreadable (written by a newer version?): forget it rather than block the batch.
                await self._eval(_CANCEL, text_of(_text(job_id)))
                continue
            claimed.append(msgspec.structs.replace(job, due=now) if retried == 1 else job)
        return claimed

    @override
    async def done(self, job: Job) -> None:
        await self._eval(_DONE, job.id)

    async def _eval(self, script: str, *arguments: str | bytes) -> object:
        try:
            answer: object = await self._redis.eval(script, len(self._keys), *self._keys, *arguments)
        except RedisError as error:
            raise JobStoreError(str(error)) from error
        return answer


def _text(value: object) -> bytes | str:
    if not isinstance(value, bytes | str):
        msg = f"Redis answered with {value!r} where a job was expected"
        raise JobStoreError(msg)
    return value


def _decode(data: bytes | str) -> Job:
    try:
        return _DECODER.decode(text_of(data))
    except msgspec.DecodeError as error:
        msg = f"a stored job could not be read: {error}"
        raise JobStoreError(msg) from error


def _readable(data: bytes | str) -> Job | None:
    """The job, or `None` (logged) when it cannot be read."""
    try:
        return _decode(data)
    except JobStoreError as error:
        _log.warning("skipping %s", error)
        return None
