"""Shoal's own defaults for the client. Nothing here is defined anywhere else."""

from typing import Final

GUILD_READY_TIMEOUT: Final = 2.0
"""Seconds a shard waits for the next startup `GUILD_CREATE` before it counts as ready anyway.
Readiness never waits for member chunking."""

MEMBER_LIST_MEMBERS_PER_SECOND: Final = 10_000
"""How fast `guild.chunk()` expects members to arrive, which sets its timeout for a large guild (a
million members: 100 seconds). A heuristic: Discord sends up to 1,000 members per chunk."""

MEMBER_LIST_MIN_TIMEOUT: Final = 5.0
"""Seconds `guild.chunk()` waits at least for every member to arrive."""

MEMBER_QUERY_TIMEOUT: Final = 30.0
"""Seconds `guild.query_members()` waits for its answer."""
