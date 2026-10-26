"""Shoal: a fully typed Discord API library for bots of every size.

The package is split into layers that can be used on their own:

- `shoal.core`: dependency-free primitives (snowflakes, flags, enums, the codec).
- `shoal.payloads`: typed mirrors of every Discord JSON object, one module per docs page.
- `shoal.rest`: the HTTP client and rate limiter, usable without a gateway (dashboards, workers).
- `shoal.gateway`: shards, compression, identify scheduling and resumable sessions.
- `shoal.cache`: a policy-driven cache that survives restarts and knows how fresh each entry is.
- `shoal.ipc`: streams gateway events from gateway processes to worker processes.
- `shoal.metrics`: exporters for the metrics every layer records (Prometheus).
- `shoal.diagnostics`: event loop health (`LoopMonitor`).
- `shoal.endpoint`: receives interactions over HTTP, for bots without a gateway.
"""

from shoal._version import __version__

__all__ = ["__version__"]
