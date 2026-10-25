"""Running many shards: one process (a cluster) or many processes and hosts.

A bot with `shard_count` shards can run them all in one process, or split them into clusters, one per
process or machine. `cluster_shard_ids` decides which shards a cluster owns; `ShardManager` runs
those shards with one identify limiter, one connector and one session store between them.

Clusters in different processes coordinate through the same protocols the shards already use: pass
an `IdentifyLimiter` backed by shared storage so clusters never exceed `max_concurrency` together,
and a `SessionStore` on shared disk or a database so a restarted cluster resumes its shards.

    # cluster 2 of 4, all reading the same Get Gateway Bot answer
    manager = ShardManager(
        token=token,
        intents=Intents.default(),
        dispatch=handle,
        shard_count=gateway.shards,
        shard_ids=cluster_shard_ids(2, 4, gateway.shards),
        identify_limiter=LocalIdentifyLimiter(gateway.session_start_limit.max_concurrency),
    )
    await manager.run()

Discord: https://docs.discord.com/developers/events/gateway#sharding
"""

import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import final

from shoal.core.clock import Clock
from shoal.core.dispatch import DispatchHandler
from shoal.core.metrics import Metrics
from shoal.gateway.connection import AiohttpGatewayConnector, GatewayConnector
from shoal.gateway.session import SessionStore
from shoal.gateway.shard import GatewayFatalError, Shard
from shoal.gateway.sharding import IdentifyLimiter, LocalIdentifyLimiter, shard_for_guild
from shoal.payloads.gateway import DEFAULT_GATEWAY_URL, Intents, TransportCompression
from shoal.payloads.gateway_events import UpdatePresence

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
        gateway_url: The URL from Get Gateway Bot.
        compression: Transport compression for every shard.
        presence: Initial presence for every shard.
        metrics: Shared by every shard.
        clock: Time source for the shards and the default identify limiter.

    Discord: https://docs.discord.com/developers/events/gateway#sharding
    """

    __slots__ = ("_connector", "_owns_connector", "_shard_count", "_shards", "_tasks")

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
        gateway_url: str = DEFAULT_GATEWAY_URL,
        compression: TransportCompression | None = TransportCompression.ZLIB_STREAM,
        presence: UpdatePresence | None = None,
        metrics: Metrics | None = None,
        clock: Clock | None = None,
    ) -> None:
        """Create the shards; see the class docstring for the arguments. Call `run` to connect."""
        ids = list(shard_ids) if shard_ids is not None else list(range(shard_count))
        if not ids:
            msg = "a ShardManager needs at least one shard"
            raise ValueError(msg)
        if len(set(ids)) != len(ids):
            msg = "shard_ids contains duplicates"
            raise ValueError(msg)
        self._shard_count: int = shard_count
        self._owns_connector: bool = connector is None
        self._connector: GatewayConnector = connector or AiohttpGatewayConnector()
        limiter = identify_limiter or LocalIdentifyLimiter(1, clock=clock)
        self._shards: dict[int, Shard] = {
            shard_id: Shard(
                token=token,
                shard_id=shard_id,
                shard_count=shard_count,
                intents=intents,
                dispatch=dispatch,
                connector=self._connector,
                identify_limiter=limiter,
                session_store=session_store,
                gateway_url=gateway_url,
                compression=compression,
                presence=presence,
                metrics=metrics,
                clock=clock,
            )
            for shard_id in sorted(ids)
        }
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def shards(self) -> Mapping[int, Shard]:
        """The shards this manager runs, by ID."""
        return self._shards

    @property
    def shard_count(self) -> int:
        """Total shards of the bot, across every cluster."""
        return self._shard_count

    def shard_for_guild(self, guild_id: int) -> Shard | None:
        """The shard that receives a guild's events, if this manager runs it."""
        return self._shards.get(shard_for_guild(guild_id, self._shard_count))

    async def run(self) -> None:
        """Run every shard until `close` is called.

        Shards connect concurrently; the identify limiter decides how many identify at once. If any
        shard fails fatally (bad token, disallowed intents), every shard is closed and the error is
        raised, because the same cause would stop the others too.

        Raises:
            GatewayFatalError: A shard was closed with a code reconnecting cannot fix.
        """
        self._tasks = [
            asyncio.create_task(shard.run(), name=f"shoal-shard-{shard_id}")
            for shard_id, shard in self._shards.items()
        ]
        try:
            for finished in asyncio.as_completed(self._tasks):
                await finished
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
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks = []
            if self._owns_connector:
                await self._connector.close()

    async def close(self, *, resumable: bool = True) -> None:
        """Close every shard. With `resumable`, sessions are saved so a restart resumes them."""
        await asyncio.gather(*(shard.close(resumable=resumable) for shard in self._shards.values()))
