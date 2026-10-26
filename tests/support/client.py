"""A logged-in `Client` whose REST calls are answered by a `FakeTransport`, and an event recorder.

client, transport = await logged_in()
events = Recorder(client, "message", "message_edit")
await feed(client, "MESSAGE_CREATE", {...})
assert events.names() == ["message"]
"""

from typing import overload

import msgspec

from shoal.client.client import Client, Listener
from shoal.core.dispatch import DispatchEvent
from shoal.payloads import Intents
from shoal.rest.client import RestClient, Token
from tests.support.fakes import FakeTransport, settle
from tests.support.json_payloads import APPLICATION
from tests.support.models import APPLICATION as APPLICATION_ID
from tests.support.models import BOT, GUILD, guild_create, user
from tests.support.rest import make_client

INTENTS = Intents.default().with_flags(guild_members=True, guild_presences=True, message_content=True)


@overload
async def logged_in() -> tuple[Client, FakeTransport]: ...
@overload
async def logged_in[C: Client](kind: type[C]) -> tuple[C, FakeTransport]: ...
async def logged_in(kind: type[Client] = Client) -> tuple[Client, FakeTransport]:
    """A client of class `kind` that logged in as `BOT` of application `APPLICATION_ID`."""
    transport = FakeTransport()

    def rest(token: Token) -> RestClient:
        return make_client(transport, token=token)

    client = kind(intents=INTENTS, rest=rest)
    transport.queue(200, user(BOT, "shoalbot") | {"bot": True})
    transport.queue(200, APPLICATION | {"id": str(APPLICATION_ID)})
    await client.login("token")
    return client, transport


async def feed(client: Client, name: str, data: object, *, shard: int = 0) -> None:
    """Feed one dispatch and let the handlers it starts run."""
    await client.feed(DispatchEvent(shard, name, None, msgspec.Raw(msgspec.json.encode(data))))
    await settle()


@overload
async def started() -> tuple[Client, FakeTransport]: ...
@overload
async def started[C: Client](kind: type[C]) -> tuple[C, FakeTransport]: ...
async def started(kind: type[Client] = Client) -> tuple[Client, FakeTransport]:
    """A logged-in client that received `READY` and the test guild."""
    client, transport = await logged_in(kind)
    await feed(client, "READY", {
        "v": 10,
        "user": user(BOT, "shoalbot") | {"bot": True},
        "guilds": [{"id": str(GUILD), "unavailable": True}],
        "session_id": "s",
        "resume_gateway_url": "wss://resume.example",
        "application": {"id": str(APPLICATION_ID), "flags": 0},
    })  # fmt: skip
    await feed(client, "GUILD_CREATE", guild_create())
    return client, transport


class Recorder:
    """Records every emission of the named events, in order."""

    def __init__(self, client: Client, *names: str) -> None:
        self.seen: list[tuple[str, tuple[object, ...]]] = []
        for name in names:
            client.add_listener(self._listener(name), name)

    def _listener(self, name: str) -> Listener:
        async def record(*args: object) -> None:
            self.seen.append((name, args))

        record.__name__ = f"on_{name}"
        return record

    def names(self) -> list[str]:
        return [name for name, _ in self.seen]

    def args(self, name: str) -> tuple[object, ...]:
        """The arguments of the only emission of `name`."""
        [found] = [args for seen, args in self.seen if seen == name]
        return found
