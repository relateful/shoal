"""Gateway sessions shared by every process of a bot, in Redis.

    manager = ShardManager(..., session_store=RedisSessionStore(redis))

A shard that moves to another host after a deploy resumes the session its old process saved. Each
session expires `max_age` after it was last saved, so a stale one is never tried.

A session with the bot token can resume it: keep Redis private to the bot.
"""

import logging
from typing import final, override

from shoal.core.codec import PayloadDecodeError, decode_json, encode_json
from shoal.gateway.defaults import RESUME_WINDOW
from shoal.gateway.session import GatewaySession, SessionStore
from shoal.redis.base import Redis, key_of, text_of
from shoal.redis.defaults import KEY_PREFIX

_log = logging.getLogger("shoal.redis")


@final
class RedisSessionStore(SessionStore):
    """One key per shard and shard count, expiring `max_age` seconds after its last save.

    Args:
        redis: The client to store sessions with.
        prefix: What the keys start with; give each bot its own.
        max_age: Seconds after which a saved session is not worth trying. Shoal's heuristic, not a
            documented Discord limit.
    """

    __slots__ = ("_max_age", "_prefix", "_redis")

    def __init__(self, redis: Redis, *, prefix: str = KEY_PREFIX, max_age: float = RESUME_WINDOW) -> None:
        """Create a store; see the class docstring for the arguments."""
        self._redis: Redis = redis
        self._prefix: str = prefix
        self._max_age: float = max_age

    def _key(self, shard_id: int, shard_count: int) -> str:
        return key_of(self._prefix, "sessions", shard_count, shard_id)

    @override
    async def load(self, shard_id: int, shard_count: int) -> GatewaySession | None:
        data = await self._redis.get(self._key(shard_id, shard_count))
        if data is None:
            return None
        try:
            session = decode_json(text_of(data), GatewaySession)
        except PayloadDecodeError:
            _log.warning("the session saved for shard %d is corrupt; identifying a new one", shard_id)
            await self.delete(shard_id, shard_count)
            return None
        return session

    @override
    async def save(self, session: GatewaySession) -> None:
        await self._redis.set(
            self._key(session.shard_id, session.shard_count),
            encode_json(session),
            px=round(self._max_age * 1000),
        )

    @override
    async def delete(self, shard_id: int, shard_count: int) -> None:
        await self._redis.delete(self._key(shard_id, shard_count))
