import pytest

from shoal.core import metrics as metrics_module
from shoal.core.metrics import (
    ALL_METRICS,
    CACHE_LOOKUPS,
    InMemoryMetrics,
    MetricKind,
    MetricSpec,
    NoopMetrics,
)


def test_catalog_is_complete_ordered_and_unique() -> None:
    declared = {value: name for name, value in vars(metrics_module).items() if isinstance(value, MetricSpec)}
    identifiers = [declared[spec] for spec in ALL_METRICS]
    assert identifiers == sorted(identifiers)
    assert set(ALL_METRICS) == set(declared)
    assert len({spec.name for spec in ALL_METRICS}) == len(ALL_METRICS)


def test_catalog_follows_prometheus_naming() -> None:
    for spec in ALL_METRICS:
        assert spec.name.startswith("shoal_")
        assert spec.name.endswith("_total") == (spec.kind is MetricKind.COUNTER)
        assert spec.description.endswith(".")
        if spec.kind is MetricKind.HISTOGRAM:
            assert spec.name.endswith("_seconds")


def test_in_memory_metrics_record_by_series() -> None:
    metrics = InMemoryMetrics()
    labels = {"kind": "user", "result": "hit"}
    metrics.increment(CACHE_LOOKUPS, labels)
    metrics.increment(CACHE_LOOKUPS, labels, 2)
    assert metrics.counters[InMemoryMetrics.key(CACHE_LOOKUPS, labels)] == 3


def test_in_memory_metrics_reject_mislabelled_calls() -> None:
    with pytest.raises(ValueError, match="expects labels"):
        InMemoryMetrics().increment(CACHE_LOOKUPS, {"kind": "user"})


def test_noop_metrics_accept_anything() -> None:
    metrics = NoopMetrics()
    metrics.increment(CACHE_LOOKUPS)
    metrics.set(CACHE_LOOKUPS, 1)
    metrics.observe(CACHE_LOOKUPS, 1)
