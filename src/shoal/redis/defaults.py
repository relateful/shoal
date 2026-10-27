"""Shoal's own defaults for the Redis implementations. Nothing here is defined anywhere else."""

from typing import Final

EVENT_BATCH: Final = 100
"""Stream entries read at once."""

EVENT_CLAIM_AFTER: Final = 60.0
"""Seconds an event read by a group's consumer may stay unfinished before another consumer takes it."""

EVENT_GROUP_BATCH: Final = 10
"""Stream entries a group consumer reads at once: few, since another consumer may take over an
entry that waits too long in this one's batch."""

EVENT_READ_BLOCK: Final = 1.0
"""Seconds one read waits for new events; how long `close` can take to end an iteration."""

EVENT_RECONNECT_BACKOFF_CAP: Final = 30.0
"""The longest backoff, in seconds, between reads while Redis cannot be reached."""

EVENT_STREAM_MAX_LENGTH: Final = 100_000
"""About how many events the stream keeps for consumers that are behind or away."""

JOB_LEASE: Final = 300.0
"""Seconds a claimed scheduled job is held before another process may run it again (its process
is taken to have died); longer than handlers take."""

KEY_BATCH: Final = 1000
"""Keys read or deleted in one command."""

KEY_PREFIX: Final = "shoal"
"""What every key starts with unless a bot is given its own prefix."""
