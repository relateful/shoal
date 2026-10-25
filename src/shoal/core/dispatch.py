"""The dispatch event every layer passes around.

A shard produces `DispatchEvent`s, the cache consumes them, and the IPC layer carries them between
processes. Keeping the type in `shoal.core` lets those layers share it without depending on each other.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import msgspec

from shoal.core.codec import decode_json


@dataclass(frozen=True, slots=True)
class DispatchEvent:
    """One opcode 0 Dispatch, with its data left as the raw JSON Discord sent.

    The data is decoded only by whoever needs it, into the type they need, so forwarding an event
    (to another process, a queue, a log) never pays for parsing it.

    Discord: https://docs.discord.com/developers/events/gateway#dispatch-events
    """

    shard_id: int
    name: str
    sequence: int | None
    data: msgspec.Raw

    def decode[T](self, target: type[T]) -> T:
        """Decode the event data into `target`.

        Raises:
            PayloadDecodeError: The data does not match `target`.
        """
        return decode_json(self.data, target)


type DispatchHandler = Callable[[DispatchEvent], Awaitable[None]]
"""Receives dispatch events in order."""
