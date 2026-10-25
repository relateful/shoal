"""Metrics export.

The catalog and the `Metrics` protocol live in `shoal.core.metrics` so every layer can report without
depending on an exporter. Exporters live here: `shoal.metrics.prometheus` needs the `prometheus` extra
and is imported explicitly.
"""

from shoal.core.metrics import (
    ALL_METRICS,
    InMemoryMetrics,
    MetricKind,
    Metrics,
    MetricSpec,
    NoopMetrics,
)

__all__ = ["ALL_METRICS", "InMemoryMetrics", "MetricKind", "MetricSpec", "Metrics", "NoopMetrics"]
