# Diagnosing a slow bot

A Discord bot runs on one event loop. A single blocking call (`requests.get`, `time.sleep`, a
synchronous database driver, heavy CPU work) stops everything: heartbeats are late, Discord drops
the connection, and events queue up. The logs then show the consequences, not the cause.

## Find the blocking call

```python
from shoal.diagnostics import LoopMonitor

async with LoopMonitor(threshold=0.25, metrics=metrics):
    await manager.run()
```

When the loop stops responding for longer than `threshold`, a watchdog thread captures the event
loop's stack **while it is blocked** and logs it:

```
event loop blocked for 0.512s so far; likely culprit: /app/cogs/music.py:42 in search
  File "/app/cogs/music.py", line 42, in search
    response = requests.get(url)
```

The culprit is the innermost frame outside the standard library and installed packages. When the loop
recovers, the total block time is logged. With `metrics=` (see [metrics](metrics.md)), blocks are
counted in `shoal_loop_blocks_total`, their durations in `shoal_loop_block_seconds`, and the loop's
scheduling lag in `shoal_loop_lag_seconds`. `on_block=` receives each report as a `BlockReport`, for
example to forward it to an error tracker.

## Notice events arriving late

Each shard compares the time a message or interaction was created (from its snowflake) with when its
event arrived. When the gap passes five seconds it warns, with the heartbeat latency for comparison:

```
shard 0: MESSAGE_CREATE arrived 15.0s after it was created, while heartbeat latency is 50ms.
Events are queuing before your code sees them: check for a blocked event loop ...
```

A high delay with a low latency means the time is lost on your side, usually a blocked loop. The
delay is always recorded as `shoal_gateway_event_delay_seconds`; set `event_delay_warning=None` on the
shard to silence the warning. A system clock that is out of sync also shows up here, so keep NTP on.
