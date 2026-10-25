"""Shoal's own diagnostics defaults. Nothing here is defined anywhere else."""

from typing import Final

LOOP_BLOCK_THRESHOLD: Final = 0.25
"""Seconds the event loop may go without running the monitor's tick before a block is reported."""

LOOP_CHECK_INTERVAL: Final = 0.05
"""Seconds between the monitor's ticks and the watchdog's checks."""
