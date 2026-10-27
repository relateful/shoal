"""Settings for one cluster, read once from the environment and checked at start."""

import os
from dataclasses import dataclass


class ConfigError(Exception):
    """A setting is missing or invalid; the message says which."""


def _number(name: str, default: str) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        msg = f"{name} must be a number"
        raise ConfigError(msg) from None


@dataclass(frozen=True, slots=True)
class Settings:
    token: str
    prefix: str
    redis_url: str
    cluster_id: int
    """Which cluster this process is, from 0."""
    cluster_count: int
    shard_count: int
    """Every cluster must agree on it; the shards are split between them."""
    max_concurrency: int
    """From `GET /gateway/bot`: how many shards may identify at once, across every cluster."""

    @property
    def name(self) -> str:
        return f"cluster-{self.cluster_id}"

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("DISCORD_TOKEN", "").strip()
        if not token:
            msg = "DISCORD_TOKEN is not set (copy .env.example to .env and fill it in)"
            raise ConfigError(msg)
        settings = cls(
            token=token,
            prefix=os.environ.get("BOT_PREFIX", "!"),
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            cluster_id=_number("CLUSTER_ID", "0"),
            cluster_count=_number("CLUSTER_COUNT", "1"),
            shard_count=_number("SHARD_COUNT", "1"),
            max_concurrency=_number("MAX_CONCURRENCY", "1"),
        )
        if not 0 <= settings.cluster_id < settings.cluster_count <= settings.shard_count:
            msg = "need 0 <= CLUSTER_ID < CLUSTER_COUNT <= SHARD_COUNT"
            raise ConfigError(msg)
        return settings
