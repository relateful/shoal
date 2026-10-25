import socket
import urllib.request

from prometheus_client import generate_latest

from shoal.core.metrics import ALL_METRICS, CACHE_LOOKUPS, LOOP_BLOCK_SECONDS, REST_INVALID_REQUESTS
from shoal.metrics.prometheus import PrometheusMetrics


def test_every_metric_is_registered_up_front() -> None:
    exported = generate_latest(PrometheusMetrics().registry).decode()
    for spec in ALL_METRICS:
        assert f"# HELP {spec.name}" in exported


def test_values_are_exported_with_their_labels() -> None:
    metrics = PrometheusMetrics(namespace_labels={"bot": "main"})
    metrics.increment(CACHE_LOOKUPS, {"kind": "user", "result": "hit"}, 2)
    metrics.set(REST_INVALID_REQUESTS, 7)
    metrics.observe(LOOP_BLOCK_SECONDS, 0.3)
    exported = generate_latest(metrics.registry).decode()
    assert 'shoal_cache_lookups_total{bot="main",kind="user",result="hit"} 2.0' in exported
    assert 'shoal_rest_invalid_requests{bot="main"} 7.0' in exported
    assert 'shoal_loop_block_seconds_count{bot="main"} 1.0' in exported


def test_unlabelled_metrics_work_without_namespace_labels() -> None:
    metrics = PrometheusMetrics()
    metrics.set(REST_INVALID_REQUESTS, 3)
    assert "shoal_rest_invalid_requests 3.0" in generate_latest(metrics.registry).decode()


def test_kind_mismatches_are_ignored_rather_than_raised() -> None:
    metrics = PrometheusMetrics()
    metrics.increment(REST_INVALID_REQUESTS)
    metrics.set(CACHE_LOOKUPS, 1, {"kind": "user", "result": "hit"})
    metrics.observe(REST_INVALID_REQUESTS, 1)
    assert "shoal_rest_invalid_requests 0.0" in generate_latest(metrics.registry).decode()


def test_serve_exposes_the_registry_over_http() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    metrics = PrometheusMetrics()
    metrics.set(REST_INVALID_REQUESTS, 5)
    metrics.serve(port)
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5) as response:
        assert b"shoal_rest_invalid_requests 5.0" in response.read()
