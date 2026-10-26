"""The gateway send limit: 120 events per connection per 60 seconds.

Exceeding it disconnects the shard immediately, so the limiter keeps a few slots in reserve for
heartbeats, which must never be delayed behind presence updates or member requests.

Discord: https://docs.discord.com/developers/events/gateway#rate-limiting
"""

from collections import deque
from typing import final

from shoal.core.clock import Clock
from shoal.gateway.defaults import HEARTBEAT_RESERVED_SENDS
from shoal.payloads.gateway import GATEWAY_SEND_LIMIT, GATEWAY_SEND_WINDOW


@final
class GatewaySendLimiter:
    """A sliding window over sent events, with `reserved` slots only priority sends may use."""

    __slots__ = ("_clock", "_limit", "_reserved", "_sent", "_window")

    def __init__(
        self,
        clock: Clock,
        *,
        limit: int = GATEWAY_SEND_LIMIT,
        window: float = GATEWAY_SEND_WINDOW,
        reserved: int = HEARTBEAT_RESERVED_SENDS,
    ) -> None:
        """Create a limiter for one connection."""
        if not 0 <= reserved < limit:
            msg = "reserved must be between 0 and limit - 1"
            raise ValueError(msg)
        self._clock: Clock = clock
        self._limit: int = limit
        self._window: float = window
        self._reserved: int = reserved
        self._sent: deque[float] = deque()  # bounded by the window: at most `limit` sends in it

    async def acquire(self, *, priority: bool = False) -> None:
        """Wait until an event may be sent, then count it. Heartbeats pass `priority=True`."""
        allowed = self._limit if priority else self._limit - self._reserved
        while True:
            now = self._clock.monotonic()
            while self._sent and self._sent[0] <= now - self._window:
                self._sent.popleft()
            if len(self._sent) < allowed:
                self._sent.append(now)
                return
            await self._clock.sleep(self._sent[0] + self._window - now)
