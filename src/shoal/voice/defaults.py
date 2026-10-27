"""Shoal's own voice defaults. Nothing here is defined anywhere else."""

from typing import Final

FIRST_LOSS_SAMPLES: Final = 960
"""Samples per channel concealed for a packet lost before any of its stream was decoded, so no packet
says how long one is (20 ms, the length Opus encoders default to). Every later loss takes the
length of the last packet decoded, from its TOC byte."""

IP_DISCOVERY_TIMEOUT: Final = 5.0
"""Seconds to wait for the voice server's IP discovery answer."""

JOIN_TIMEOUT: Final = 30.0
"""Seconds to wait for Discord to answer a voice state update with the voice server, and for the
voice handshake to finish."""

MAX_CONCEALED: Final = 5
"""Lost packets in a row that are concealed (about 100 ms); a longer gap is a pause, left silent."""

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

REORDER_DEPTH: Final = 3
"""Packets a received stream holds for a late one before taking it for lost (about 60 ms)."""

RESUME_ATTEMPTS: Final = 5
"""Resumes tried in a row before a voice connection gives up."""

RESUME_BACKOFF_CAP: Final = 30.0
"""The longest backoff, in seconds, between attempts to reconnect a voice connection."""

STABLE_SESSION: Final = 60.0
"""Seconds a resumed voice session must last before losing it again starts a new count of attempts."""

UNANSWERED_HEARTBEATS: Final = 2
"""Voice heartbeats left unanswered before the socket is taken for dead and resumed."""

UNNAMED_PACKETS: Final = 50
"""Packets held per audio stream whose sender Discord has not named yet (about a second), so the
start of what someone says is not lost to a late Speaking message; the oldest go first."""

UNNAMED_STREAMS: Final = 16
"""Unnamed audio streams held at once; a new one beyond this drops the oldest stream's packets."""
