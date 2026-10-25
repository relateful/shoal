"""Dependency-free primitives shared by every other layer.

Nothing here touches the network; `shoal.core` may import only the standard library and msgspec.
`write_private` writes a local file when called, and callers run it through `asyncio.to_thread`.
"""

from msgspec import UNSET, UnsetType

from shoal.core.backoff import backoff_delay
from shoal.core.clock import Clock, SystemClock
from shoal.core.codec import (
    PayloadDecodeError,
    decode_json,
    decode_msgpack,
    encode_json,
    encode_msgpack,
    json_decoder,
    msgpack_decoder,
)
from shoal.core.dispatch import DispatchEvent, DispatchHandler
from shoal.core.enums import DiscordIntEnum, DiscordStrEnum
from shoal.core.errors import MissingDependencyError, ShoalError
from shoal.core.flags import BaseFlags, flag
from shoal.core.metrics import InMemoryMetrics, MetricKind, Metrics, MetricSpec, NoopMetrics
from shoal.core.snowflake import DISCORD_EPOCH_MS, Snowflake

__all__ = [
    "DISCORD_EPOCH_MS",
    "UNSET",
    "BaseFlags",
    "Clock",
    "DiscordIntEnum",
    "DiscordStrEnum",
    "DispatchEvent",
    "DispatchHandler",
    "InMemoryMetrics",
    "MetricKind",
    "MetricSpec",
    "Metrics",
    "MissingDependencyError",
    "NoopMetrics",
    "PayloadDecodeError",
    "ShoalError",
    "Snowflake",
    "SystemClock",
    "UnsetType",
    "backoff_delay",
    "decode_json",
    "decode_msgpack",
    "encode_json",
    "encode_msgpack",
    "flag",
    "json_decoder",
    "msgpack_decoder",
]
