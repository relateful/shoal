"""Coordination between clusters: which process runs which shard, and commands for shards run elsewhere.

A bot split into clusters still acts as one. A command for a guild (joining a voice channel,
requesting members) has to go out on the shard that guild is on, whichever process runs it, and a
reshard has to hand over in every cluster at once. Two protocols carry that between processes:

- a `ShardDirectory`, where every `ShardManager` reports the state of its shards, so any process sees
  the whole bot (which cluster runs each shard, which are ready, their latency) and a reshard knows
  when every new shard is ready;
- a `CommandRouter`, which delivers a gateway command to the process running its shard.

`MemoryShardDirectory` and `MemoryCommandRouter` serve managers in one process; `shoal.redis` has
implementations shared through Redis.

Discord: https://docs.discord.com/developers/events/gateway#sharding
"""

import asyncio
from collections.abc import AsyncGenerator, Collection, Mapping, Sequence
from typing import Final, Protocol, final, override

import msgspec

from shoal.core.clock import Clock, SystemClock
from shoal.core.codec import decode_json
from shoal.gateway.defaults import COMMAND_QUEUE_SIZE, SHARD_STATUS_TTL
from shoal.gateway.shard import ShardState
from shoal.payloads.gateway import GatewayOpcode
from shoal.payloads.gateway_events import (
    RequestChannelInfo,
    RequestGuildMembers,
    RequestSoundboardSounds,
    UpdatePresence,
    UpdateVoiceState,
)

COMMAND_TYPES: Final[Mapping[GatewayOpcode, type[msgspec.Struct]]] = {
    GatewayOpcode.PRESENCE_UPDATE: UpdatePresence,
    GatewayOpcode.REQUEST_CHANNEL_INFO: RequestChannelInfo,
    GatewayOpcode.REQUEST_GUILD_MEMBERS: RequestGuildMembers,
    GatewayOpcode.REQUEST_SOUNDBOARD_SOUNDS: RequestSoundboardSounds,
    GatewayOpcode.VOICE_STATE_UPDATE: UpdateVoiceState,
}
"""The payload each gateway command is decoded into on the process that sends it to Discord."""


class ShardStatus(msgspec.Struct, frozen=True, kw_only=True):
    """What one shard is doing, as its cluster last reported it.

    Attributes:
        shard_id: The shard.
        shard_count: The shard count it was identified with.
        cluster: The name of the `ShardManager` running it.
        state: Where it is in its connection lifecycle.
        latency: Its last heartbeat round trip in seconds, once measured.
        reported_at: When it was reported, in seconds since the epoch.
    """

    shard_id: int
    shard_count: int
    cluster: str
    state: ShardState
    latency: float | None
    reported_at: float


class GatewayCommand(msgspec.Struct, frozen=True, kw_only=True):
    """A gateway command on its way to the process running its shard.

    Attributes:
        shard_id: The shard to send it on.
        shard_count: The shard count `shard_id` belongs to.
        opcode: The command (`GatewayOpcode.is_command`).
        data: The command's payload, as JSON.
    """

    shard_id: int
    shard_count: int
    opcode: GatewayOpcode
    data: msgspec.Raw

    def payload(self) -> msgspec.Struct:
        """The command's payload, decoded into its type in `COMMAND_TYPES`.

        Raises:
            ValueError: `opcode` is not a command.
            PayloadDecodeError: `data` does not match it.
        """
        kind = COMMAND_TYPES.get(self.opcode)
        if kind is None:
            msg = f"{self.opcode.name} is not a gateway command"
            raise ValueError(msg)
        return decode_json(self.data, kind)


class ShardDirectory(Protocol):
    """Where every cluster reports its shards, and anyone reads the whole bot's."""

    __slots__ = ()

    async def report(self, statuses: Sequence[ShardStatus]) -> None:
        """Record the latest status of each shard in `statuses`."""
        ...

    async def statuses(self, shard_count: int) -> dict[int, ShardStatus]:
        """The latest status of every shard of `shard_count` reported within the directory's TTL."""
        ...


class CommandRouter(Protocol):
    """Delivers gateway commands to the process running their shard."""

    __slots__ = ()

    async def send(self, command: GatewayCommand) -> bool:
        """Deliver `command`; `False` when no process receives commands for its shard."""
        ...

    def receive(self, shard_count: int, shard_ids: Collection[int]) -> AsyncGenerator[GatewayCommand]:
        """Yield the commands sent to these shards until the iteration is closed."""
        ...


@final
class MemoryShardDirectory(ShardDirectory):
    """A directory for the managers of one process.

    Args:
        ttl: Seconds a status counts after it was reported; a cluster that stops reporting drops out.
        clock: Time source.
    """

    __slots__ = ("_clock", "_statuses", "_ttl")

    def __init__(self, *, ttl: float = SHARD_STATUS_TTL, clock: Clock | None = None) -> None:
        """Create an empty directory; see the class docstring for the arguments."""
        self._ttl: float = ttl
        self._clock: Clock = clock or SystemClock()
        self._statuses: dict[tuple[int, int], ShardStatus] = {}

    @override
    async def report(self, statuses: Sequence[ShardStatus]) -> None:
        for status in statuses:
            self._statuses[status.shard_count, status.shard_id] = status

    @override
    async def statuses(self, shard_count: int) -> dict[int, ShardStatus]:
        oldest = self._clock.wall() - self._ttl
        for key in [key for key, status in self._statuses.items() if status.reported_at < oldest]:
            del self._statuses[key]
        return {
            shard_id: status for (count, shard_id), status in self._statuses.items() if count == shard_count
        }


@final
class MemoryCommandRouter(CommandRouter):
    """Routes commands between the managers of one process.

    Args:
        queue_size: Commands held for a shard whose manager has not taken them yet; past it, the
            oldest is dropped.
    """

    __slots__ = ("_queue_size", "_receivers")

    def __init__(self, *, queue_size: int = COMMAND_QUEUE_SIZE) -> None:
        """Create a router; see the class docstring for the arguments."""
        self._queue_size: int = queue_size
        self._receivers: dict[tuple[int, int], asyncio.Queue[GatewayCommand]] = {}

    @override
    async def send(self, command: GatewayCommand) -> bool:
        queue = self._receivers.get((command.shard_count, command.shard_id))
        if queue is None:
            return False
        if queue.full():
            _ = queue.get_nowait()
        queue.put_nowait(command)
        return True

    @override
    async def receive(self, shard_count: int, shard_ids: Collection[int]) -> AsyncGenerator[GatewayCommand]:
        queue: asyncio.Queue[GatewayCommand] = asyncio.Queue(self._queue_size)
        keys = [(shard_count, shard_id) for shard_id in shard_ids]
        for key in keys:
            self._receivers[key] = queue
        try:
            while True:
                yield await queue.get()
        finally:
            for key in keys:
                if self._receivers.get(key) is queue:
                    del self._receivers[key]
