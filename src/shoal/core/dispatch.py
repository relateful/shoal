"""The dispatch event every layer passes around.

A shard produces `DispatchEvent`s, the cache consumes them, and the IPC layer carries them between
processes. Keeping the type in `shoal.core` lets those layers share it without depending on each other.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import cast

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
    _decoded: dict[type[object], object] = field(
        default_factory=dict[type[object], object], init=False, compare=False, repr=False
    )
    """Each type the data was decoded into: the cache and the client decode the same event, and only
    the first pays. Decoded payloads are never changed in place, so sharing one is safe."""

    def decode[T](self, target: type[T]) -> T:
        """Decode the event data into `target`, once per target.

        Raises:
            PayloadDecodeError: The data does not match `target`.
        """
        found = self._decoded.get(target)
        if found is None:
            found = decode_json(self.data, target)
            self._decoded[target] = found
        return cast("T", found)  # stored under `target` just above, by this method only


type DispatchHandler = Callable[[DispatchEvent], Awaitable[None]]
"""Receives dispatch events in order."""
