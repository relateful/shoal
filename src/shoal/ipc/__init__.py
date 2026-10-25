"""Inter-process communication: run gateways and bot logic in separate processes.

A gateway process runs the shards and an `EventServer`; any number of worker processes connect with
an `EventClient` and receive the dispatches they subscribe to (by shard and by event name). Workers
can restart, deploy and scale without touching the gateway connection, which keeps its sessions.

No broker is required: the protocol is length-prefixed msgpack over TCP, authenticated with a shared
secret. Workers send their HTTP requests through `shoal.rest` directly or through a REST proxy.
"""

from shoal.ipc import defaults
from shoal.ipc.client import EventClient
from shoal.ipc.protocol import PROTOCOL_VERSION, IPCError
from shoal.ipc.server import EventServer

__all__ = ["PROTOCOL_VERSION", "EventClient", "EventServer", "IPCError", "defaults"]
