"""Shoal's own IPC defaults. Nothing here is defined anywhere else."""

from typing import Final

CLIENT_CONNECT_TIMEOUT: Final = 10.0
"""Seconds a client waits for a TCP connection before the attempt counts as failed."""

CLIENT_RECONNECT_BACKOFF_CAP: Final = 30.0
"""The longest backoff, in seconds, between a client's reconnection attempts."""

HANDSHAKE_MAX_FRAME_SIZE: Final = 64 * 1024
"""The largest hello accepted from a client that has not authenticated yet, in bytes."""

HANDSHAKE_TIMEOUT: Final = 10.0
"""Seconds a new connection has to authenticate before it is closed."""

MAX_FRAME_SIZE: Final = 32 * 1024 * 1024
"""The largest frame accepted, in bytes. A `GUILD_CREATE` for a very large guild can be several MB."""

SUBSCRIBER_QUEUE_SIZE: Final = 10_000
"""Events buffered per subscriber. A subscriber that falls this far behind is disconnected (and
reconnects) rather than letting the gateway process's memory grow without bound."""
