"""Shoal's own defaults for the models. Nothing here is defined anywhere else."""

from typing import Final

DEFAULT_BAN_MESSAGE_SECONDS: Final = 86_400
"""How much of a banned member's recent messages `Member.ban` and `Guild.ban` delete unless told
otherwise: one day. Discord's own default is none; pass
`delete_message_seconds=0` for that."""

TYPING_REFRESH: Final = 5.0
"""Seconds between typing indicators while `typing()` is active; each lasts about 10 seconds."""
