"""Shoal's own defaults for the core helpers. Nothing here is defined anywhere else."""

from typing import Final

COOLDOWN_PRUNE_ABOVE: Final = 1024
"""How many keys a cooldown holds before it starts forgetting keys whose window has passed."""

COOLDOWN_PRUNE_INTERVAL: Final = 60.0
"""Seconds between those scans at most, however long the cooldown's window is."""
