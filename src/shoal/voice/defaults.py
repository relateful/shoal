"""Shoal's own voice defaults. Nothing here is defined anywhere else."""

from typing import Final

IP_DISCOVERY_TIMEOUT: Final = 5.0
"""Seconds to wait for the voice server's IP discovery answer."""

JOIN_TIMEOUT: Final = 30.0
"""Seconds to wait for Discord to answer a voice state update with the voice server, and for the
voice handshake to finish."""

PLAYBACK_MAX_LAG: Final = 0.2
"""Seconds playback may fall behind its schedule (a stalled event loop) before it stops catching up
and starts the schedule over, rather than send a burst of packets."""

RECEIVED_PACKETS_QUEUE_SIZE: Final = 512
"""Voice packets held for a reader that falls behind (about ten seconds of one speaker) before the
oldest are dropped."""

REJOIN_ATTEMPTS: Final = 5
"""Times in a row a voice client joins its channel again after losing its session, before it leaves."""

REJOIN_BACKOFF_CAP: Final = 30.0
"""The longest wait, in seconds, between those attempts."""

RESUME_ATTEMPTS: Final = 5
"""Resumes tried in a row before a voice connection gives up."""

RESUME_BACKOFF_CAP: Final = 30.0
"""The longest backoff, in seconds, between attempts to reconnect a voice connection."""

STABLE_SESSION: Final = 60.0
"""Seconds a resumed voice session must last before losing it again starts a new count of attempts."""

UNANSWERED_HEARTBEATS: Final = 2
"""Voice heartbeats left unanswered before the socket is taken for dead and resumed."""
