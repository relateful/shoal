"""Running many shards: one process (a cluster) or many processes and hosts.

A bot with `shard_count` shards can run them all in one process, or split them into clusters, one per
process or machine. `cluster_shard_ids` decides which shards a cluster owns; `ShardManager` runs
those shards with one identify limiter, one connector and one session store between them.

Clusters in different processes coordinate through shared implementations of a few protocols:

- an `IdentifyLimiter`, so the clusters together never identify more than `max_concurrency` at once;
- a `SessionStore`, so a cluster restarted elsewhere resumes its shards;
- a `ShardDirectory`, where each cluster reports its shards, so every process sees the whole bot and
  a reshard hands over in every cluster at once;
- a `CommandRouter`, so a command for a guild on another cluster's shard (joining a voice channel,
  requesting members) is sent by the cluster running that shard.

    # cluster 2 of 4, all reading the same Get Gateway Bot answer
    manager = ShardManager(
        token=token,
        intents=Intents.default(),
        dispatch=handle,
        shard_count=gateway.shards,
        shard_ids=cluster_shard_ids(2, 4, gateway.shards),
        identify_limiter=RedisIdentifyLimiter(redis, max_concurrency=max_concurrency),
        session_store=RedisSessionStore(redis),
        directory=RedisShardDirectory(redis),
        router=RedisCommandRouter(redis),
        name="cluster-2",
    )
    await manager.run()

`reshard` moves to a new shard count without downtime: the new shards identify beside the running
ones, their events held back, and once every new shard of the bot is ready each cluster switches to
them and closes the old ones.

Discord: https://docs.discord.com/developers/events/gateway#sharding
"""

import asyncio
import contextlib
import logging
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Unpack, final

import msgspec

from shoal.core.backoff import backoff_delay
from shoal.core.clock import Clock, SystemClock, sleep_unless
from shoal.core.codec import PayloadDecodeError, encode_json
from shoal.core.dispatch import DispatchEvent, DispatchHandler
from shoal.core.metrics import Metrics
from shoal.core.snowflake import Snowflake
from shoal.core.tasks import cancel_and_wait
from shoal.gateway.cluster import CommandRouter, GatewayCommand, ShardDirectory, ShardStatus
from shoal.gateway.connection import AiohttpGatewayConnector, GatewayConnector
from shoal.gateway.defaults import RECONNECT_BACKOFF_CAP, RESHARD_POLL_INTERVAL, SHARD_STATUS_INTERVAL
from shoal.gateway.session import SessionStore
from shoal.gateway.shard import GatewayFatalError, Shard, ShardNotConnectedError, ShardOptions, ShardState
from shoal.gateway.sharding import IdentifyLimiter, LocalIdentifyLimiter, shard_for_guild
from shoal.payloads.gateway import GatewayOpcode, Intents
from shoal.payloads.gateway_events import RequestSoundboardSounds, UpdatePresence

_log = logging.getLogger("shoal.gateway.manager")


def cluster_shard_ids(cluster_id: int, cluster_count: int, shard_count: int) -> range:
    """The contiguous block of shard IDs owned by one cluster.

    Shards are split as evenly as possible; the first `shard_count % cluster_count` clusters take one
    extra shard. Contiguous blocks keep each cluster's identify buckets together, so a cluster with a
    shared identify limiter starts its shards in as few five-second rounds as possible.

    Raises:
        ValueError: The IDs or counts are out of range.
    """
    if cluster_count < 1 or shard_count < cluster_count:
        msg = "need at least one cluster and at least one shard per cluster"
        raise ValueError(msg)
    if not 0 <= cluster_id < cluster_count:
        msg = f"cluster_id {cluster_id} is outside 0..{cluster_count - 1}"
        raise ValueError(msg)
    base, extra = divmod(shard_count, cluster_count)
    start = cluster_id * base + min(cluster_id, extra)
    size = base + (1 if cluster_id < extra else 0)
    return range(start, start + size)


@final
class _Gate:
    """Passes a generation's events on while it is the live one."""

    __slots__ = ("_dispatch", "open")

    def __init__(self, dispatch: DispatchHandler, *, open_: bool) -> None:
        self._dispatch: DispatchHandler = dispatch
        self.open: bool = open_

    async def __call__(self, event: DispatchEvent) -> None:
        if self.open:
            await self._dispatch(event)


@dataclass(eq=False, slots=True)
class _Generation:
    """The shards of one shard count, with what runs them."""

    shard_count: int
    shards: dict[int, Shard]
    gate: _Gate
    tasks: list[asyncio.Task[None]] = field(default_factory=list[asyncio.Task[None]])
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    """Set when the manager closes while this generation waits to take over."""


@final
class ShardManager:
    """Runs a set of shards of one bot in this process.

    Args:
        token: The bot token, without the `Bot ` prefix.
        intents: Gateway intents for every shard.
        dispatch: Receives every dispatch from every shard (`DispatchEvent.shard_id` tells them apart).
        shard_count: Total shards of the bot, across every cluster.
        shard_ids: The shards this manager runs. Defaults to all of them.
        identify_limiter: Shared by every shard. Defaults to a local limiter with `max_concurrency` 1;
            pass the bot's real `max_concurrency` from Get Gateway Bot to start faster.
        connector: Shared websocket connector. Defaults to one aiohttp session for all shards.
        session_store: Where shard sessions are saved for resuming after a restart.
        presence: Initial presence for every shard.
        metrics: Shared by every shard.
        clock: Time source for the shards and the default identify limiter.
        directory: Where this manager reports its shards every `SHARD_STATUS_INTERVAL` seconds, and
            where a reshard learns that every cluster's new shards are ready.
        router: Carries commands for shards other managers run, and brings this manager the
            commands for its own.
        name: How this manager appears in the directory: give each cluster its own.
        options: How every shard connects (`ShardOptions`): `gateway_url`, `compression`,
            `large_threshold`, `capabilities`, `event_delay_warning`, `resume_window`.

    Raises:
        ValueError: `shard_ids` is empty or holds a duplicate.

    Discord: https://docs.discord.com/developers/events/gateway#sharding
    """

    __slots__ = (
        "_clock",
        "_connector",
        "_directory",
        "_dispatch",
        "_generation",
        "_identify_limiter",
        "_intents",
        "_metrics",
        "_name",
        "_options",
        "_outcome",
        "_owns_connector",
        "_pending",
        "_presence",
        "_random_source",
        "_router",
        "_session_store",
        "_token",
    )

    def __init__(
        self,
        *,
        token: str,
        intents: Intents,
        dispatch: DispatchHandler,
        shard_count: int,
        shard_ids: Sequence[int] | None = None,
        identify_limiter: IdentifyLimiter | None = None,
        connector: GatewayConnector | None = None,
        session_store: SessionStore | None = None,
        presence: UpdatePresence | None = None,
        metrics: Metrics | None = None,
        clock: Clock | None = None,
        directory: ShardDirectory | None = None,
        router: CommandRouter | None = None,
        name: str = "main",
        **options: Unpack[ShardOptions],
    ) -> None:
        """Create the shards; see the class docstring for the arguments. Call `run` to connect."""
        self._token: str = token
        self._intents: Intents = intents
        self._dispatch: DispatchHandler = dispatch
        self._owns_connector: bool = connector is None
        self._connector: GatewayConnector = connector or AiohttpGatewayConnector()
        self._identify_limiter: IdentifyLimiter = identify_limiter or LocalIdentifyLimiter(1, clock=clock)
        self._session_store: SessionStore | None = session_store
        self._presence: UpdatePresence | None = presence
        self._metrics: Metrics | None = metrics
        self._clock: Clock = clock or SystemClock()
        self._directory: ShardDirectory | None = directory
        self._router: CommandRouter | None = router
        self._name: str = name
        self._random_source: random.Random = random.Random()  # noqa: S311 - jitter, not security
        self._options: ShardOptions = options
        self._generation: _Generation = self._new_generation(
            shard_count, shard_ids, live=True, session_store=session_store
        )
        self._pending: _Generation | None = None
        self._outcome: asyncio.Future[None] | None = None

    def _new_generation(
        self,
        shard_count: int,
        shard_ids: Sequence[int] | None,
        *,
        live: bool,
        session_store: SessionStore | None,
    ) -> _Generation:
        ids = list(shard_ids) if shard_ids is not None else list(range(shard_count))
        if not ids:
            msg = "a ShardManager needs at least one shard"
            raise ValueError(msg)
        if len(set(ids)) != len(ids):
            msg = "shard_ids contains duplicates"
            raise ValueError(msg)
        gate = _Gate(self._dispatch, open_=live)
        shards = {
            shard_id: Shard(
                token=self._token,
                shard_id=shard_id,
                shard_count=shard_count,
                intents=self._intents,
                dispatch=gate,
                connector=self._connector,
                identify_limiter=self._identify_limiter,
                session_store=session_store,
                presence=self._presence,
                metrics=self._metrics,
                clock=self._clock,
                **self._options,
            )
            for shard_id in sorted(ids)
        }
        return _Generation(shard_count, shards, gate)

    @property
    def shards(self) -> Mapping[int, Shard]:
        """The shards this manager runs, by ID (during a reshard, the ones still handling events)."""
        return self._generation.shards

    @property
    def shard_count(self) -> int:
        """Total shards of the bot, across every cluster."""
        return self._generation.shard_count

    @property
    def name(self) -> str:
        """How this manager appears in the shard directory."""
        return self._name

    def shard_for_guild(self, guild_id: int) -> Shard | None:
        """The shard that receives a guild's events, if this manager runs it."""
        return self.shards.get(shard_for_guild(guild_id, self.shard_count))

    def statuses(self) -> list[ShardStatus]:
        """The status of every shard this manager runs, including a reshard's new ones."""
        now = self._clock.wall()
        generations = [self._generation] if self._pending is None else [self._generation, self._pending]
        return [
            ShardStatus(
                shard_id=shard.shard_id,
                shard_count=generation.shard_count,
                cluster=self._name,
                state=shard.state,
                latency=shard.latency,
                reported_at=now,
            )
            for generation in generations
            for shard in generation.shards.values()
        ]

    async def send_command(self, shard_id: int, opcode: GatewayOpcode, data: msgspec.Struct) -> None:
        """Send a gateway command on shard `shard_id`, whichever manager runs it.

        Raises:
            ValueError: `opcode` is not a command, or no manager runs the shard (with no router, any
                shard this manager does not run).
            ShardNotConnectedError: The shard is not connected.
        """
        shard = self.shards.get(shard_id)
        if shard is not None:
            await shard.send_command(opcode, data)
            return
        if not opcode.is_command:
            msg = f"{opcode.name} is managed by the shard and cannot be sent directly"
            raise ValueError(msg)
        command = GatewayCommand(
            shard_id=shard_id,
            shard_count=self.shard_count,
            opcode=opcode,
            data=msgspec.Raw(encode_json(data)),
        )
        if self._router is None or not await self._router.send(command):
            msg = f"shard {shard_id} is not run by this manager, and no other manager receives its commands"
            raise ValueError(msg)

    async def send_to_guild(self, guild_id: int, opcode: GatewayOpcode, data: msgspec.Struct) -> None:
        """Send a gateway command on the shard of `guild_id`, whichever manager runs it.

        Raises:
            ValueError: As for `send_command`.
            ShardNotConnectedError: The shard is not connected.
        """
        await self.send_command(shard_for_guild(guild_id, self.shard_count), opcode, data)

    async def update_presence(self, presence: UpdatePresence) -> None:
        """Change the bot's presence on every shard this manager runs (each cluster sets its own).

        A reshard's new shards take it too: those not connected yet identify with it.

        Raises:
            ShardNotConnectedError: A shard handling events is not connected.

        Discord: https://docs.discord.com/developers/events/gateway-events#update-presence
        """
        self._presence = presence
        pending = self._pending
        if pending is not None:
            await asyncio.gather(*(_present(shard, presence) for shard in pending.shards.values()))
        await asyncio.gather(*(shard.update_presence(presence) for shard in self.shards.values()))

    async def request_soundboard_sounds(self, guild_ids: Iterable[int]) -> None:
        """Ask each guild's shard for its soundboard sounds (answered by `SOUNDBOARD_SOUNDS` dispatches).

        The answers arrive on the process running each guild's shard.

        Raises:
            ValueError: A guild is on a shard no manager runs (with no router, any shard this
                manager does not run).

        Discord: https://docs.discord.com/developers/events/gateway-events#request-soundboard-sounds
        """
        by_shard: dict[int, list[Snowflake]] = {}
        for guild_id in guild_ids:
            shard_id = shard_for_guild(guild_id, self.shard_count)
            if shard_id not in self.shards and self._router is None:
                msg = f"guild {guild_id} is on shard {shard_id}, which this manager does not run"
                raise ValueError(msg)
            by_shard.setdefault(shard_id, []).append(Snowflake(guild_id))
        await asyncio.gather(
            *(
                self.send_command(
                    shard_id, GatewayOpcode.REQUEST_SOUNDBOARD_SOUNDS, RequestSoundboardSounds(guild_ids=ids)
                )
                for shard_id, ids in by_shard.items()
            )
        )

    async def run(self) -> None:
        """Run every shard until `close` is called.

        Shards connect concurrently; the identify limiter decides how many identify at once. If any
        shard fails fatally (bad token, disallowed intents), every shard is closed and the error is
        raised, because the same cause would stop the others too.

        Raises:
            GatewayFatalError: A shard was closed with a code reconnecting cannot fix.
        """
        self._outcome = asyncio.get_running_loop().create_future()
        self._start(self._generation)
        reporter = asyncio.create_task(self._report(), name=f"shoal-shards-{self._name}")
        try:
            await self._outcome
        except asyncio.CancelledError:
            # Stopped from outside (`asyncio.run` ending, a task cancelled) rather than by `close`:
            # save the sessions first, or the next start identifies every shard again.
            await self.close(resumable=True)
            raise
        except GatewayFatalError:
            _log.exception("a shard failed fatally; closing every shard in this manager")
            await self.close(resumable=False)
            raise
        except Exception:
            # Shards recover from connection errors themselves; reaching here is a bug. The other
            # shards close resumably so a restart picks their sessions up.
            _log.exception("a shard crashed; closing every shard in this manager")
            await self.close(resumable=True)
            raise
        finally:
            await cancel_and_wait(reporter)
            for generation in self._generations():
                await self._stop(generation)
            if self._owns_connector:
                await self._connector.close()

    async def close(self, *, resumable: bool = True) -> None:
        """Close every shard. With `resumable`, sessions are saved so a restart resumes them.

        A reshard in progress is abandoned: its new shards close for good.
        """
        pending, self._pending = self._pending, None
        if pending is not None:
            pending.closed.set()
            await asyncio.gather(*(shard.close(resumable=False) for shard in pending.shards.values()))
            await self._stop(pending)
        await asyncio.gather(
            *(shard.close(resumable=resumable) for shard in self._generation.shards.values())
        )
        if self._outcome is not None and not self._outcome.done():
            self._outcome.set_result(None)

    async def reshard(self, shard_count: int, shard_ids: Sequence[int] | None = None) -> None:
        """Move to `shard_count` shards without downtime, while `run` is running.

        The new shards (`shard_ids`, all of them by default) identify beside the running ones, their
        events held back. Once every new shard is ready (with a `directory`, every shard of the new
        count across every cluster; call `reshard` in each cluster with its own share), this manager
        switches to them in one step and closes the old shards. An event Discord sends to both
        sessions around that moment may be dispatched twice, or by neither cluster if they switch
        apart.

        Each new shard is a new session: make sure the day's session starts cover them
        (`wait_for_session_starts`). Cancel the call to abandon the reshard; the old shards keep
        running.

        Raises:
            RuntimeError: `run` is not running, another reshard is in progress, or the manager was
                closed during the reshard.
            ValueError: `shard_count` is the current count (both would report and receive commands
                as the same shards), or `shard_ids` is empty or holds a duplicate.
        """
        if self._outcome is None or self._outcome.done():
            msg = "reshard needs the manager to be running"
            raise RuntimeError(msg)
        if self._pending is not None:
            msg = "a reshard is already in progress"
            raise RuntimeError(msg)
        if shard_count == self.shard_count:
            msg = f"the bot already runs {shard_count} shards"
            raise ValueError(msg)
        # No store yet: the new shards must not overwrite the sessions of the shards they replace.
        new = self._new_generation(shard_count, shard_ids, live=False, session_store=None)
        self._pending = new
        self._start(new)
        try:
            await self._until_ready(new)
        except BaseException:
            if self._pending is new:
                self._pending = None
                await self._stop(new)
            raise
        old = self._generation
        # One step, with no await between: no event is dispatched by both generations or by neither.
        old.gate.open = False
        new.gate.open = True
        self._generation, self._pending = new, None
        _log.info("resharded from %d to %d shards; closing the old shards", old.shard_count, new.shard_count)
        # Past the switch there is no going back: a caller giving up must not leave the old shards
        # open or the new ones without their session store.
        await asyncio.shield(self._retire(old, new))

    async def _retire(self, old: _Generation, new: _Generation) -> None:
        await asyncio.gather(*(shard.close(resumable=False) for shard in old.shards.values()))
        await self._stop(old)
        if self._session_store is not None:
            store = self._session_store
            await asyncio.gather(*(shard.keep_sessions(store) for shard in new.shards.values()))

    def _generations(self) -> list[_Generation]:
        return [self._generation] if self._pending is None else [self._generation, self._pending]

    def _start(self, generation: _Generation) -> None:
        generation.tasks = [
            asyncio.create_task(self._run_shard(shard), name=f"shoal-shard-{shard.shard_id}")
            for shard in generation.shards.values()
        ]
        if self._router is not None:
            generation.tasks.append(
                asyncio.create_task(self._receive_commands(generation), name=f"shoal-commands-{self._name}")
            )

    async def _stop(self, generation: _Generation) -> None:
        for task in generation.tasks:
            task.cancel()
        await asyncio.gather(*generation.tasks, return_exceptions=True)
        generation.tasks = []

    async def _run_shard(self, shard: Shard) -> None:
        try:
            await shard.run()
        except Exception as error:  # noqa: BLE001 - handed to `run`, which closes every shard and raises it
            if self._outcome is not None and not self._outcome.done():
                self._outcome.set_exception(error)

    async def _until_ready(self, generation: _Generation) -> None:
        wanted = set(range(generation.shard_count)) if self._directory is not None else set(generation.shards)
        while True:
            if self._pending is not generation:
                msg = "the manager was closed during the reshard"
                raise RuntimeError(msg)
            ready = {
                shard_id for shard_id, shard in generation.shards.items() if shard.state is ShardState.READY
            }
            if ready == set(generation.shards) and self._directory is not None:
                await self._publish()
                ready |= await self._ready_elsewhere(generation.shard_count)
            if wanted <= ready:
                return
            await sleep_unless(self._clock, RESHARD_POLL_INTERVAL, generation.closed)

    async def _ready_elsewhere(self, shard_count: int) -> set[int]:
        """The shards of `shard_count` the directory lists as ready; none while it cannot be read."""
        if self._directory is None:
            return set()
        try:
            statuses = await self._directory.statuses(shard_count)
        except Exception:  # noqa: BLE001 - the reshard waits and asks again; its new shards stay connected
            _log.exception("could not read the shard directory; asking again")
            return set()
        return {shard_id for shard_id, status in statuses.items() if status.state is ShardState.READY}

    async def _report(self) -> None:
        if self._directory is None:
            return
        while True:
            await self._publish()
            await self._clock.sleep(SHARD_STATUS_INTERVAL)

    async def _publish(self) -> None:
        if self._directory is None:
            return
        try:
            await self._directory.report(self.statuses())
        except Exception:  # noqa: BLE001 - the shards run on; the directory only lags until the next report
            _log.exception("could not report the shards to the directory")

    async def _receive_commands(self, generation: _Generation) -> None:
        """Send the commands routed to this generation's shards, receiving again after any failure."""
        if self._router is None:
            return
        failures = 0
        while True:
            try:
                async with contextlib.aclosing(
                    self._router.receive(generation.shard_count, generation.shards)
                ) as commands:
                    async for command in commands:
                        failures = 0
                        await _send_routed(generation, command)
            except Exception:  # noqa: BLE001 - logged; routed commands would otherwise stop for good
                _log.exception("receiving routed gateway commands failed")
            failures += 1
            delay = backoff_delay(failures, cap=RECONNECT_BACKOFF_CAP, random_source=self._random_source)
            _log.warning("receiving routed gateway commands again in %.1fs", delay)
            await self._clock.sleep(delay)


async def _present(shard: Shard, presence: UpdatePresence) -> None:
    """Give a shard that is not handling events yet its presence; one not connected identifies with it."""
    with contextlib.suppress(ShardNotConnectedError):
        await shard.update_presence(presence)


async def _send_routed(generation: _Generation, command: GatewayCommand) -> None:
    # The command names its shard in its own body: it may not be one of these.
    shard = generation.shards.get(command.shard_id)
    if shard is None:
        _log.warning(
            "skipping a routed %s for shard %d, which is not run here", command.opcode.name, command.shard_id
        )
        return
    try:
        await shard.send_command(command.opcode, command.payload())
    except (ValueError, ShardNotConnectedError, PayloadDecodeError, OSError) as error:
        _log.warning("could not send a routed %s on shard %d: %s", command.opcode.name, shard.shard_id, error)
