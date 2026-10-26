"""What the Redis implementations share: the client type, keys, and Redis's clock in scripts."""

from typing import Final

from shoal.core.errors import MissingDependencyError

try:
    from redis.asyncio import Redis
except ImportError as error:  # pragma: no cover - exercised only without the extra installed
    _FEATURE = "Redis-backed shared state"
    raise MissingDependencyError(_FEATURE, "redis") from error

__all__ = ["NOW_MS", "Redis", "key_of", "text_of"]

NOW_MS: Final = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
"""
"""Lua that sets `now` to Redis's own time in milliseconds, the same for every host."""


def key_of(prefix: str, *parts: object) -> str:
    """The key for `parts` under `prefix`: `shoal:sessions:3`."""
    return ":".join([prefix, *(str(part) for part in parts)])


def text_of(value: bytes | str) -> bytes:
    """A value read from Redis as bytes, whether the client decodes responses or not."""
    return value.encode() if isinstance(value, str) else value
