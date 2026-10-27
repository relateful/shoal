"""Shoal's own scheduler defaults. Nothing here is defined anywhere else."""

from typing import Final

CLAIM_BATCH: Final = 100
"""Due jobs claimed from the store at once; with more due, the next batch follows straight after."""

CLOCK_SKEW_WAIT: Final = 1.0
"""Seconds to wait when a job is due by this host's clock but a shared store has not released it
yet (its clock is behind), instead of asking again at once."""

IDLE_WAIT: Final = 3600.0
"""Seconds the timer sleeps with no jobs at all; adding one wakes it at once."""

MISFIRE_GRACE: Final = 60.0
"""Seconds late a job may run before it counts as missed (its `misfire` policy then applies)."""

SHARED_POLL: Final = 5.0
"""Longest wait between looks at a shared store, where other processes add jobs without waking this one."""

STORE_RETRY: Final = 5.0
"""Seconds the timer waits after the job store failed (Redis unreachable) before trying again."""
