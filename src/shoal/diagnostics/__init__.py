"""Runtime health checks: a blocked event loop, and events arriving late.

`LoopMonitor` names the code that blocks the event loop. Event delivery delay (how long after a
message was created its event arrived) is measured by each `Shard` and exported as
`shoal_gateway_event_delay_seconds`.
"""

from shoal.diagnostics import defaults
from shoal.diagnostics.loop import BlockReport, LoopMonitor

__all__ = ["BlockReport", "LoopMonitor", "defaults"]
