"""Reading a fake Redis back in tests."""

from typing import cast

from redis.asyncio import Redis

from shoal.redis.base import text_of


async def keys_of(redis: Redis, pattern: str = "*") -> list[str]:
    """Every key matching `pattern`, sorted."""
    found: object = await redis.eval("return redis.call('KEYS', ARGV[1])", 0, pattern)
    assert isinstance(found, list)
    # isinstance narrows to list[Unknown]; KEYS answers names, bytes unless the client decodes.
    return sorted(text_of(key).decode() for key in cast("list[bytes | str]", found))
