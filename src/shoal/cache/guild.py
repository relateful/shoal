"""The guild as the cache holds it."""

from datetime import datetime

from msgspec import UNSET, UnsetType

from shoal.payloads.guild import Guild


class CachedGuild(Guild):
    """A `Guild` plus the fields only `GUILD_CREATE` carries, kept across `GUILD_UPDATE` and restarts.

    `roles` and `emojis` are always empty: those live in their own collections, so each object has
    exactly one cached copy. `member_count` follows member joins and leaves after `GUILD_CREATE`.
    The extra fields are `UNSET` for a guild that was cached without a `GUILD_CREATE` (from REST).

    Discord: https://docs.discord.com/developers/events/gateway-events#guild-create
    """

    joined_at: datetime | UnsetType = UNSET
    large: bool | UnsetType = UNSET
    member_count: int | UnsetType = UNSET
