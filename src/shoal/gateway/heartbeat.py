"""Heartbeat bookkeeping: when to beat, latency, and zombie detection.

Discord: https://docs.discord.com/developers/events/gateway#sending-heartbeats
"""

from typing import final


@final
class HeartbeatMonitor:
    """Tracks heartbeats sent and acknowledged on one connection.

    A connection is a zombie when the previous heartbeat was never acknowledged by the time the next
    one is due. Discord says to close it with a code other than 1000/1001 and resume.

    Discord: https://docs.discord.com/developers/events/gateway#heartbeat-interval
    """

    __slots__ = ("_acked", "_interval", "_last_sent", "_latency")

    def __init__(self, interval_ms: int) -> None:
        """Create a monitor from Hello's `heartbeat_interval` (milliseconds)."""
        if interval_ms <= 0:
            msg = "heartbeat interval must be positive"
            raise ValueError(msg)
        self._interval: float = interval_ms / 1000
        self._last_sent: float | None = None
        self._latency: float | None = None
        self._acked: bool = True

    @property
    def interval(self) -> float:
        """Seconds between heartbeats."""
        return self._interval

    @property
    def latency(self) -> float | None:
        """Seconds between the last heartbeat and its acknowledgement, once one has been measured."""
        return self._latency

    def first_delay(self, jitter: float) -> float:
        """Seconds to wait before the first heartbeat: `interval * jitter`, jitter in [0, 1).

        Discord: https://docs.discord.com/developers/events/gateway#heartbeat-interval
        """
        if not 0.0 <= jitter < 1.0:
            msg = "jitter must be in [0, 1)"
            raise ValueError(msg)
        return self._interval * jitter

    def is_zombie(self) -> bool:
        """Whether the last heartbeat went unacknowledged."""
        return not self._acked

    def sent(self, now: float) -> None:
        """Record a heartbeat sent at monotonic time `now`."""
        self._last_sent = now
        self._acked = False

    def acknowledged(self, now: float) -> None:
        """Record a Heartbeat ACK received at monotonic time `now`.

        Only the ACK of a pending heartbeat measures latency; an ACK of a heartbeat Discord asked for
        (opcode 1) arrives when nothing is pending and would measure from the wrong beat.
        """
        if not self._acked and self._last_sent is not None:
            self._latency = now - self._last_sent
        self._acked = True
