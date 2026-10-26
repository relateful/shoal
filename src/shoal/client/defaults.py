"""Shoal's own defaults for the client. Nothing here is defined anywhere else."""

from typing import Final

GUILD_READY_TIMEOUT: Final = 2.0
"""Seconds a shard waits for the next startup `GUILD_CREATE` before it counts as ready anyway.
Readiness never waits for member chunking."""
