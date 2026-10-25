"""Prometheus export for Shoal's metrics (`pip install 'shoal[prometheus]'`).

    from shoal.metrics.prometheus import PrometheusMetrics

    metrics = PrometheusMetrics()
    metrics.serve(9100)  # http://localhost:9100/metrics for Prometheus to scrape
    rest = RestClient(token, metrics=metrics)

Every metric in `shoal.core.metrics.ALL_METRICS` is registered up front, so dashboards see every
series (at zero) from the first scrape. `docs/guide/metrics.md` lists them with example queries.
"""

from collections.abc import Mapping
from typing import Final, final, override

from shoal.core.errors import MissingDependencyError
from shoal.core.metrics import ALL_METRICS, MetricKind, Metrics, MetricSpec

try:
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, start_http_server
except ImportError as error:  # pragma: no cover - exercised only without the extra installed
    _FEATURE = "Prometheus metrics"
    raise MissingDependencyError(_FEATURE, "prometheus") from error

REQUEST_BUCKETS: Final = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
"""Histogram buckets in seconds, sized for Discord API round trips."""

type _Metric = Counter | Gauge | Histogram


@final
class PrometheusMetrics(Metrics):
    """Sends Shoal's metrics to a Prometheus registry.

    Args:
        registry: The registry to register into. Defaults to a private registry, so Shoal's metrics
            never collide with the application's own default registry.
        namespace_labels: Constant labels added to every series, for example `{"bot": "main"}` when
            several bots share one Prometheus.
    """

    __slots__ = ("_constant", "_metrics", "registry")

    def __init__(
        self,
        registry: CollectorRegistry | None = None,
        *,
        namespace_labels: Mapping[str, str] | None = None,
    ) -> None:
        """Register every Shoal metric; see the class docstring for the arguments."""
        self.registry: CollectorRegistry = registry or CollectorRegistry()
        self._constant: dict[str, str] = dict(namespace_labels or {})
        self._metrics: dict[str, _Metric] = {spec.name: self._create(spec) for spec in ALL_METRICS}

    def _create(self, spec: MetricSpec) -> _Metric:
        labels = (*self._constant, *spec.labels)
        name = spec.name.removesuffix("_total") if spec.kind is MetricKind.COUNTER else spec.name
        if spec.kind is MetricKind.COUNTER:
            return Counter(name, spec.description, labels, registry=self.registry)
        if spec.kind is MetricKind.GAUGE:
            return Gauge(name, spec.description, labels, registry=self.registry)
        return Histogram(name, spec.description, labels, registry=self.registry, buckets=REQUEST_BUCKETS)

    def _child(self, spec: MetricSpec, labels: Mapping[str, str] | None) -> _Metric:
        metric = self._metrics[spec.name]
        values = {**self._constant, **(labels or {})}
        if not values:
            return metric
        return metric.labels(**values)

    @override
    def increment(
        self, spec: MetricSpec, labels: Mapping[str, str] | None = None, value: float = 1.0
    ) -> None:
        metric = self._child(spec, labels)
        if isinstance(metric, Counter):
            metric.inc(value)

    @override
    def set(self, spec: MetricSpec, value: float, labels: Mapping[str, str] | None = None) -> None:
        metric = self._child(spec, labels)
        if isinstance(metric, Gauge):
            metric.set(value)

    @override
    def observe(self, spec: MetricSpec, value: float, labels: Mapping[str, str] | None = None) -> None:
        metric = self._child(spec, labels)
        if isinstance(metric, Histogram):
            metric.observe(value)

    def serve(self, port: int, address: str = "127.0.0.1") -> None:
        """Serve `/metrics` on a background thread for Prometheus to scrape.

        Binds to localhost by default; pass `address="0.0.0.0"` only when the port is firewalled.
        """
        start_http_server(port, addr=address, registry=self.registry)
