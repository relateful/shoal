"""Helpers and the running server fixture shared by the IPC tests."""

import asyncio
import random
from collections.abc import AsyncIterator, Sequence

import msgspec
import pytest

from shoal.core.dispatch import DispatchEvent
from shoal.ipc.client import EventClient
from shoal.ipc.server import EventServer
from tests.support.fakes import FakeClock

TOKEN = "secret"


def event(shard_id: int, name: str, sequence: int = 1) -> DispatchEvent:
    return DispatchEvent(shard_id, name, sequence, msgspec.Raw(b'{"n":' + str(sequence).encode() + b"}"))


@pytest.fixture
async def server() -> AsyncIterator[EventServer]:
    instance = EventServer(token=TOKEN)
    await instance.start()
    yield instance
    await asyncio.wait_for(instance.close(), timeout=5)


def client(
    server: EventServer,
    *,
    token: str = TOKEN,
    shard_ids: Sequence[int] | None = None,
    events: Sequence[str] | None = None,
) -> EventClient:
    host, port = server.address
    return EventClient(
        host,
        port,
        token=token,
        name="test",
        shard_ids=shard_ids,
        events=events,
        clock=FakeClock(),
        random_source=random.Random(0),
    )


async def wait_for_subscribers(server: EventServer, count: int) -> None:
    for _ in range(500):
        if server.subscriber_count == count:
            return
        await asyncio.sleep(0.01)
    msg = f"expected {count} subscribers, have {server.subscriber_count}"
    raise AssertionError(msg)
