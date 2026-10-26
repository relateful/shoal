"""Metrics: one catalog of everything Shoal measures, and a sink protocol to export it.

Every layer reports through `Metrics`. The default `NoopMetrics` costs a method call; pass a
`PrometheusMetrics` (`pip install 'shoal[prometheus]'`) or your own implementation to export to
Prometheus, StatsD, OpenTelemetry or anything else.

All metric definitions live in this module so names, units and labels stay consistent. Label values
are always bounded: routes are reported by template (`GET /channels/{channel_id}/messages`), never by
the filled-in path, so a busy bot cannot explode the series count.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol, final, override


class MetricKind(StrEnum):
    """How a metric's values combine."""

    COUNTER = "counter"
    """Only goes up. Prometheus names end in `_total`."""
    GAUGE = "gauge"
    """Goes up and down; the last value wins."""
    HISTOGRAM = "histogram"
    """Distribution of observations (durations, in seconds)."""


@dataclass(frozen=True, slots=True)
class MetricSpec:
    """The definition of one metric."""

    name: str
    kind: MetricKind
    description: str
    labels: tuple[str, ...] = ()


CACHE_LOOKUPS: Final = MetricSpec(
    "shoal_cache_lookups_total",
    MetricKind.COUNTER,
    "Cache reads, by entity kind and result (hit, stale, miss).",
    ("kind", "result"),
)

EVENTS_DROPPED: Final = MetricSpec(
    "shoal_events_dropped_total",
    MetricKind.COUNTER,
    "Gateway payloads or dispatches dropped because they could not be decoded, by stage (gateway, "
    "cache) and event.",
    ("stage", "event"),
)

GATEWAY_EVENTS: Final = MetricSpec(
    "shoal_gateway_events_total",
    MetricKind.COUNTER,
    "Gateway dispatch events received.",
    ("shard", "event"),
)

GATEWAY_EVENT_DELAY_SECONDS: Final = MetricSpec(
    "shoal_gateway_event_delay_seconds",
    MetricKind.HISTOGRAM,
    "Time from a message or interaction being created (its snowflake) to its dispatch arriving.",
    ("shard", "event"),
)

GATEWAY_LATENCY_SECONDS: Final = MetricSpec(
    "shoal_gateway_latency_seconds",
    MetricKind.GAUGE,
    "Heartbeat round trip of a shard.",
    ("shard",),
)

GATEWAY_RECONNECTS: Final = MetricSpec(
    "shoal_gateway_reconnects_total",
    MetricKind.COUNTER,
    "Shard reconnections, by how the session continued (resume, identify).",
    ("shard", "mode"),
)

GATEWAY_SHARD_READY: Final = MetricSpec(
    "shoal_gateway_shard_ready",
    MetricKind.GAUGE,
    "1 while a shard is connected and ready, else 0.",
    ("shard",),
)

HTTP_INTERACTIONS: Final = MetricSpec(
    "shoal_http_interactions_total",
    MetricKind.COUNTER,
    "Interactions received over HTTP, by type and result (inline, callback, invalid_signature, "
    "malformed, handler_error, timeout).",
    ("type", "result"),
)

HTTP_INTERACTION_SECONDS: Final = MetricSpec(
    "shoal_http_interaction_seconds",
    MetricKind.HISTOGRAM,
    "Time the handler took to answer an HTTP interaction; Discord fails it after 3 seconds.",
    ("type",),
)

HTTP_WEBHOOK_EVENTS: Final = MetricSpec(
    "shoal_http_webhook_events_total",
    MetricKind.COUNTER,
    "Webhook events received over HTTP, by event (ping, unknown for a type Shoal does not know) and "
    "result (accepted, invalid_signature, malformed, handler_error).",
    ("event", "result"),
)

IPC_DISCONNECTS: Final = MetricSpec(
    "shoal_ipc_disconnects_total",
    MetricKind.COUNTER,
    "IPC subscribers disconnected, by reason (slow, closed, error, rejected).",
    ("reason",),
)

IPC_EVENTS_SENT: Final = MetricSpec(
    "shoal_ipc_events_sent_total",
    MetricKind.COUNTER,
    "Dispatch events queued to IPC subscribers.",
)

IPC_SUBSCRIBERS: Final = MetricSpec(
    "shoal_ipc_subscribers",
    MetricKind.GAUGE,
    "Worker processes currently subscribed to this gateway process's events.",
)

LOOP_BLOCKS: Final = MetricSpec(
    "shoal_loop_blocks_total",
    MetricKind.COUNTER,
    "Times the event loop was blocked for longer than the monitor's threshold.",
)

LOOP_BLOCK_SECONDS: Final = MetricSpec(
    "shoal_loop_block_seconds",
    MetricKind.HISTOGRAM,
    "How long each detected event loop block lasted.",
)

LOOP_LAG_SECONDS: Final = MetricSpec(
    "shoal_loop_lag_seconds",
    MetricKind.GAUGE,
    "How late the event loop ran the monitor's last tick; near zero on a healthy loop.",
)

REST_INVALID_REQUESTS: Final = MetricSpec(
    "shoal_rest_invalid_requests",
    MetricKind.GAUGE,
    "Invalid responses (401, 403, non-shared 429) in the current 10-minute window; Discord bans at 10,000.",
)

REST_RATE_LIMITED: Final = MetricSpec(
    "shoal_rest_rate_limited_total",
    MetricKind.COUNTER,
    "429 responses, by scope (user, global, shared, unknown).",
    ("route", "scope"),
)

REST_REQUESTS: Final = MetricSpec(
    "shoal_rest_requests_total",
    MetricKind.COUNTER,
    "HTTP responses received from Discord.",
    ("method", "route", "status"),
)

REST_REQUEST_SECONDS: Final = MetricSpec(
    "shoal_rest_request_seconds",
    MetricKind.HISTOGRAM,
    "Time from sending an HTTP request to receiving its response, excluding rate limit waits.",
    ("method", "route"),
)

REST_RETRIES: Final = MetricSpec(
    "shoal_rest_retries_total",
    MetricKind.COUNTER,
    "HTTP requests retried, by reason (rate_limited, server_error, network).",
    ("route", "reason"),
)

ALL_METRICS: Final = (
    CACHE_LOOKUPS,
    EVENTS_DROPPED,
    GATEWAY_EVENTS,
    GATEWAY_EVENT_DELAY_SECONDS,
    GATEWAY_LATENCY_SECONDS,
    GATEWAY_RECONNECTS,
    GATEWAY_SHARD_READY,
    HTTP_INTERACTIONS,
    HTTP_INTERACTION_SECONDS,
    HTTP_WEBHOOK_EVENTS,
    IPC_DISCONNECTS,
    IPC_EVENTS_SENT,
    IPC_SUBSCRIBERS,
    LOOP_BLOCKS,
    LOOP_BLOCK_SECONDS,
    LOOP_LAG_SECONDS,
    REST_INVALID_REQUESTS,
    REST_RATE_LIMITED,
    REST_REQUESTS,
    REST_REQUEST_SECONDS,
    REST_RETRIES,
)
"""Every metric Shoal reports. Exporters register these up front."""


class Metrics(Protocol):
    """Receives measurements. Implementations must be cheap and must never raise."""

    __slots__ = ()

    def increment(
        self, spec: MetricSpec, labels: Mapping[str, str] | None = None, value: float = 1.0
    ) -> None:
        """Add `value` to a counter."""
        ...

    def set(self, spec: MetricSpec, value: float, labels: Mapping[str, str] | None = None) -> None:
        """Set a gauge."""
        ...

    def observe(self, spec: MetricSpec, value: float, labels: Mapping[str, str] | None = None) -> None:
        """Record one histogram observation."""
        ...


@final
class NoopMetrics(Metrics):
    """Discards everything. The default."""

    __slots__ = ()

    @override
    def increment(
        self, spec: MetricSpec, labels: Mapping[str, str] | None = None, value: float = 1.0
    ) -> None:
        return

    @override
    def set(self, spec: MetricSpec, value: float, labels: Mapping[str, str] | None = None) -> None:
        return

    @override
    def observe(self, spec: MetricSpec, value: float, labels: Mapping[str, str] | None = None) -> None:
        return


type _SeriesKey = tuple[str, tuple[tuple[str, str], ...]]


@final
class InMemoryMetrics(Metrics):
    """Keeps every value in dictionaries. For tests and quick debugging.

    Unlike real exporters it is strict: a call whose label names differ from the metric's declared
    labels raises, so the test suite catches every mislabelled call site.
    """

    __slots__ = ("counters", "gauges", "observations")

    def __init__(self) -> None:
        """Create empty series."""
        self.counters: dict[_SeriesKey, float] = {}
        self.gauges: dict[_SeriesKey, float] = {}
        self.observations: dict[_SeriesKey, list[float]] = {}

    @staticmethod
    def key(spec: MetricSpec, labels: Mapping[str, str] | None = None) -> _SeriesKey:
        """The series key for a metric and label set."""
        given = labels or {}
        if set(given) != set(spec.labels):
            msg = f"{spec.name} expects labels {sorted(spec.labels)}, got {sorted(given)}"
            raise ValueError(msg)
        return spec.name, tuple(sorted(given.items()))

    @override
    def increment(
        self, spec: MetricSpec, labels: Mapping[str, str] | None = None, value: float = 1.0
    ) -> None:
        key = self.key(spec, labels)
        self.counters[key] = self.counters.get(key, 0.0) + value

    @override
    def set(self, spec: MetricSpec, value: float, labels: Mapping[str, str] | None = None) -> None:
        self.gauges[self.key(spec, labels)] = value

    @override
    def observe(self, spec: MetricSpec, value: float, labels: Mapping[str, str] | None = None) -> None:
        self.observations.setdefault(self.key(spec, labels), []).append(value)
