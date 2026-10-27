"""Settings, read once from the environment and checked at start."""

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """A setting is missing or invalid; the message says which."""


@dataclass(frozen=True, slots=True)
class Settings:
    token: str
    prefix: str
    log_level: str
    data_dir: Path
    """Gateway sessions and the cache snapshot: keep it on a volume, so restarts resume."""
    metrics_address: str
    metrics_port: int
    bot_name: str
    """A label on every metric, to tell bots apart on one Prometheus."""

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("DISCORD_TOKEN", "").strip()
        if not token:
            msg = "DISCORD_TOKEN is not set (copy .env.example to .env and fill it in)"
            raise ConfigError(msg)
        try:
            port = int(os.environ.get("METRICS_PORT", "9100"))
        except ValueError:
            msg = "METRICS_PORT must be a number"
            raise ConfigError(msg) from None
        return cls(
            token=token,
            prefix=os.environ.get("BOT_PREFIX", "!"),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            data_dir=Path(os.environ.get("DATA_DIR", "data")),
            metrics_address=os.environ.get("METRICS_ADDRESS", "127.0.0.1"),
            metrics_port=port,
            bot_name=os.environ.get("BOT_NAME", "bigbot"),
        )
