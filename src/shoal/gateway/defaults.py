"""Shoal's own gateway defaults: tunables and choices that are not Discord facts.

Discord-documented gateway constants (send limits, identify window, close codes) live in
`shoal.payloads.gateway`. Nothing here is defined anywhere else.
"""

from typing import Final

CONNECT_TIMEOUT: Final = 30.0
"""Seconds allowed to open a gateway websocket before the attempt counts as failed."""

DELAY_TRACKED_EVENTS: Final = frozenset({"MESSAGE_CREATE", "INTERACTION_CREATE"})
"""Dispatches whose `id` snowflake is the moment a user acted, so their delivery delay is meaningful."""

EVENT_DELAY_WARNING: Final = 5.0
"""Seconds between an object's creation and its dispatch arriving before Shoal warns."""

EVENT_DELAY_WARNING_COOLDOWN: Final = 60.0
"""Minimum seconds between two event delay warnings from one shard."""

GATEWAY_DOMAIN: Final = "discord.gg"
"""The domain a saved resume URL must be on to be trusted with the token. Discord's own gateway
hosts (and every resume URL seen so far) are on it, though the docs only show it in examples."""

HEARTBEAT_RESERVED_SENDS: Final = 5
"""Gateway send slots per window kept free for heartbeats, so commands can never delay them."""

HELLO_TIMEOUT: Final = 20.0
"""Seconds a new connection has to deliver Hello before it is treated as dead and replaced."""

INVALID_SESSION_DELAY: Final = (1.0, 5.0)
"""Bounds, in seconds, of the random wait before identifying after a non-resumable Invalid Session,
so shards invalidated together do not identify in lockstep."""

RECONNECT_BACKOFF_CAP: Final = 60.0
"""The longest backoff, in seconds, between failed connection attempts."""

RESUMABLE_CLOSE_CODE: Final = 4900
"""The code Shoal closes with when the session must stay resumable.

Closing with 1000 or 1001 makes Discord invalidate the session; any other code keeps it. 4900 is in
the private-use range and never sent by Discord.

Discord: https://docs.discord.com/developers/events/gateway#initiating-a-disconnect
"""

RESUME_WINDOW: Final = 180.0
"""Seconds after a disconnect (or since a session was saved) during which Shoal tries to resume.

Not a documented limit: Discord staff describe resumability as lasting "a few minutes" or until the
session's event buffer overflows. A resume past the real limit costs one Invalid Session round trip.
"""

STABLE_CONNECTION: Final = 60.0
"""Seconds a connection must stay ready before its loss reconnects without backoff. Shorter-lived
connections count as failures, so a gateway that accepts and then drops the shard is not hammered."""
