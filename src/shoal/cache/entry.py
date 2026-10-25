"""Cache entries and how fresh they are.

Every entry records where its value came from, when, and through which shard. That is what lets a bot
restart with a warm cache and still know which data Discord has confirmed since.
"""

from enum import IntEnum

import msgspec

from shoal.core.snowflake import Snowflake


class Source(IntEnum):
    """Where a cached value came from."""

    SNAPSHOT = 0
    """Loaded from a snapshot saved before a restart."""
    REST = 1
    """Fetched over HTTP."""
    GATEWAY = 2
    """Received in a gateway dispatch."""


class Freshness(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Provenance of one cached value."""

    source: Source
    observed_at: float
    """Unix time the value was observed."""
    revision: int
    """The store's write counter when the value was written. Every write gets a higher one, so the
    store can tell what was written before or after a session started or a guild was reconciled."""
    shard: int | None = None
    """The shard whose session delivered the value, or `None` (REST, or written by hand). The entry is
    fresh while that shard's session is the one that wrote it."""


class Entry[V](msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """A cached value with its provenance and the guild it belongs to."""

    value: V
    freshness: Freshness
    scope: Snowflake | None = None
    """The guild this entry belongs to, so a guild's entries can be reconciled together."""
