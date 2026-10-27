"""A Redis for each test: fakeredis, which runs the Lua scripts as Redis does.

Set `SHOAL_TEST_REDIS_URL` to run the same tests against a real Redis instead; its database is
emptied before each test.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from urllib.parse import urlsplit

import fakeredis
import pytest
from redis.asyncio import Redis

_REAL = os.environ.get("SHOAL_TEST_REDIS_URL")


def _blocking[**P](read: Callable[P, Awaitable[object]]) -> Callable[P, Awaitable[object]]:
    """A stream read that waits out its `block` when nothing came, as Redis does; the fake answers at once."""

    async def wait(*args: P.args, **kwargs: P.kwargs) -> object:
        answer = await read(*args, **kwargs)
        block = kwargs.get("block")
        if not answer and isinstance(block, int):
            await asyncio.sleep(block / 1000)
        return answer

    return wait


def _real_client(url: str) -> Redis:
    parts = urlsplit(url)
    return Redis(
        host=parts.hostname or "localhost", port=parts.port or 6379, db=int(parts.path.strip("/") or 0)
    )


@pytest.fixture(autouse=True)
def blocking_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    if _REAL is None:
        for name in ("xread", "xreadgroup"):
            monkeypatch.setattr(
                fakeredis.FakeAsyncRedis, name, _blocking(getattr(fakeredis.FakeAsyncRedis, name))
            )


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    if _REAL is not None:
        client = _real_client(_REAL)
        await client.eval("redis.call('FLUSHDB') return 0", 0)
    else:
        client = fakeredis.FakeAsyncRedis(server=fakeredis.FakeServer())
    yield client
    await client.aclose()


@pytest.fixture
async def other(redis: Redis) -> AsyncIterator[Redis]:
    """A second client of the same Redis: another process of the bot."""
    if _REAL is not None:
        client = _real_client(_REAL)
    else:
        client = fakeredis.FakeAsyncRedis(server=redis.connection_pool.connection_kwargs["server"])
    yield client
    await client.aclose()
