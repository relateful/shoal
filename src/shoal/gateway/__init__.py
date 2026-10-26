"""The gateway: shards, compression, identify scheduling and sessions that survive restarts.

Discord-documented gateway constants (send limits, identify window, close codes) are exported from
`shoal.payloads`; Shoal's own defaults live in `shoal.gateway.defaults`.

Discord: https://docs.discord.com/developers/events/gateway
"""

from shoal.gateway import defaults
from shoal.gateway.cluster import (
    COMMAND_TYPES,
    CommandRouter,
    GatewayCommand,
    MemoryCommandRouter,
    MemoryShardDirectory,
    ShardDirectory,
    ShardStatus,
)
from shoal.gateway.compression import (
    Decompressor,
    ZlibStreamDecompressor,
    ZstdStreamDecompressor,
    create_decompressor,
    zstd_available,
)
from shoal.gateway.connection import (
    AiohttpGatewayConnector,
    GatewayConnection,
    GatewayConnector,
    MessageKind,
    WebSocketMessage,
)
from shoal.gateway.heartbeat import HeartbeatMonitor
from shoal.gateway.manager import ShardManager, cluster_shard_ids
from shoal.gateway.ratelimit import GatewaySendLimiter
from shoal.gateway.session import FileSessionStore, GatewaySession, MemorySessionStore, SessionStore
from shoal.gateway.shard import (
    GatewayFatalError,
    PrivilegedIntentsRequiredError,
    Shard,
    ShardNotConnectedError,
    ShardState,
)
from shoal.gateway.sharding import IdentifyLimiter, LocalIdentifyLimiter, rate_limit_key, shard_for_guild

__all__ = [
    "COMMAND_TYPES",
    "AiohttpGatewayConnector",
    "CommandRouter",
    "Decompressor",
    "FileSessionStore",
    "GatewayCommand",
    "GatewayConnection",
    "GatewayConnector",
    "GatewayFatalError",
    "GatewaySendLimiter",
    "GatewaySession",
    "HeartbeatMonitor",
    "IdentifyLimiter",
    "LocalIdentifyLimiter",
    "MemoryCommandRouter",
    "MemorySessionStore",
    "MemoryShardDirectory",
    "MessageKind",
    "PrivilegedIntentsRequiredError",
    "SessionStore",
    "Shard",
    "ShardDirectory",
    "ShardManager",
    "ShardNotConnectedError",
    "ShardState",
    "ShardStatus",
    "WebSocketMessage",
    "ZlibStreamDecompressor",
    "ZstdStreamDecompressor",
    "cluster_shard_ids",
    "create_decompressor",
    "defaults",
    "rate_limit_key",
    "shard_for_guild",
    "zstd_available",
]
