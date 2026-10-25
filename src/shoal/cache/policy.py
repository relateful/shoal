"""What the cache keeps, for how long, and what happens on restart."""

from enum import StrEnum
from typing import Final

import msgspec

from shoal.cache.defaults import MESSAGE_CACHE_LIMIT, USER_CACHE_LIMIT


class EntityKind(StrEnum):
    """The kinds of Discord objects the cache can hold."""

    CHANNEL = "channel"
    EMOJI = "emoji"
    GUILD = "guild"
    MEMBER = "member"
    MESSAGE = "message"
    PRESENCE = "presence"
    ROLE = "role"
    USER = "user"
    VOICE_STATE = "voice_state"


class CachePolicy(msgspec.Struct, frozen=True, kw_only=True):
    """How one entity kind is cached.

    Attributes:
        enabled: Cache this kind at all.
        max_entries: Keep at most this many, evicting the least recently used. `None` is unbounded.
        ttl: Seconds after which an entry is dropped on access. `None` keeps entries until evicted.
        persist: Include this kind in snapshots, so it survives restarts.
    """

    enabled: bool = True
    max_entries: int | None = None
    ttl: float | None = None
    persist: bool = True

    def __post_init__(self) -> None:
        if self.max_entries is not None and self.max_entries < 1:
            msg = "max_entries must be at least 1"
            raise ValueError(msg)
        if self.ttl is not None and self.ttl <= 0:
            msg = "ttl must be positive"
            raise ValueError(msg)

    @classmethod
    def disabled(cls) -> "CachePolicy":
        """Do not cache this kind."""
        return cls(enabled=False, persist=False)


class RestartStrategy(StrEnum):
    """What the cache does when the bot starts."""

    COLD = "cold"
    """Start empty and fill from the gateway, like discord.py."""
    WARM = "warm"
    """Load the last snapshot and serve it immediately, marked stale until Discord confirms it."""


DEFAULT_POLICIES: Final = {
    EntityKind.CHANNEL: CachePolicy(),
    EntityKind.EMOJI: CachePolicy(),
    EntityKind.GUILD: CachePolicy(),
    EntityKind.MEMBER: CachePolicy(),
    EntityKind.MESSAGE: CachePolicy(max_entries=MESSAGE_CACHE_LIMIT, persist=False),
    EntityKind.PRESENCE: CachePolicy(persist=False),
    EntityKind.ROLE: CachePolicy(),
    EntityKind.USER: CachePolicy(max_entries=USER_CACHE_LIMIT),
    EntityKind.VOICE_STATE: CachePolicy(),
}
"""Everything cached. Messages are bounded (discord.py's default size) and, with presences, not
persisted: both change too often for a snapshot to be worth restoring. Users are bounded because
message authors from every guild pass through them; the other kinds mirror what Discord says the
bot's guilds contain, so they are bounded by those guilds."""


class CacheConfig(msgspec.Struct, frozen=True, kw_only=True):
    """Cache configuration.

    Attributes:
        policies: Per-kind overrides. Kinds left out use `DEFAULT_POLICIES`.
        restart: The restart strategy.
    """

    policies: dict[EntityKind, CachePolicy] = msgspec.field(default_factory=dict[EntityKind, CachePolicy])
    restart: RestartStrategy = RestartStrategy.WARM

    def policy(self, kind: EntityKind) -> CachePolicy:
        """The effective policy for `kind`."""
        return self.policies.get(kind, DEFAULT_POLICIES[kind])
