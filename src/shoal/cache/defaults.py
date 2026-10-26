"""Shoal's own cache defaults. Nothing here is defined anywhere else.

Structures built from these values (such as `DEFAULT_POLICIES`) live next to their types in
`shoal.cache.policy`.
"""

from typing import Final

MESSAGE_CACHE_LIMIT: Final = 1000
"""Messages kept in memory by default."""

SNAPSHOT_FORMAT: Final = 4
"""Bumped whenever the snapshot layout changes incompatibly; older snapshots are then ignored."""

USER_CACHE_LIMIT: Final = 100_000
"""Users kept in memory by default. Message authors would otherwise accumulate without end; members
carry their own user object, so evicting a user only costs a REST fetch for `get_user`."""

YIELD_EVERY: Final = 1000
"""Entries a long cache pass (restoring a snapshot, scanning a guild) handles between yields to the
event loop, so a large guild never blocks it."""
