# Metrics and Grafana

Every layer reports to a `Metrics` sink. The default discards everything; pass `PrometheusMetrics`
(`pip install "shoal[prometheus]"`) to export:

```python
from shoal.metrics.prometheus import PrometheusMetrics

metrics = PrometheusMetrics(namespace_labels={"bot": "main"})
metrics.serve(9100)

rest = RestClient(token, metrics=metrics)
manager = ShardManager(..., metrics=metrics)
store = CacheStore(metrics=metrics)
```

Point Prometheus at `http://host:9100/metrics` and add it as a Grafana data source. `serve` binds to
localhost unless told otherwise.

## What is recorded

| Metric | Type | Labels |
| --- | --- | --- |
| `shoal_cache_lookups_total` | counter | `kind`, `result` (`hit`, `stale`, `miss`) |
| `shoal_events_dropped_total` | counter | `stage` (`gateway`, `cache`), `event` |
| `shoal_gateway_event_delay_seconds` | histogram | `shard`, `event` |
| `shoal_gateway_events_total` | counter | `shard`, `event` |
| `shoal_gateway_latency_seconds` | gauge | `shard` |
| `shoal_gateway_reconnects_total` | counter | `shard`, `mode` (`resume`, `identify`) |
| `shoal_gateway_shard_ready` | gauge | `shard` |
| `shoal_http_interaction_seconds` | histogram | `type` |
| `shoal_http_interactions_total` | counter | `type`, `result` (`inline`, `callback`, `invalid_signature`, `malformed`, `handler_error`, `timeout`) |
| `shoal_http_webhook_events_total` | counter | `event`, `result` (`accepted`, `invalid_signature`, `malformed`, `handler_error`) |
| `shoal_ipc_disconnects_total` | counter | `reason` |
| `shoal_ipc_events_sent_total` | counter | |
| `shoal_ipc_subscribers` | gauge | |
| `shoal_loop_block_seconds` | histogram | |
| `shoal_loop_blocks_total` | counter | |
| `shoal_loop_lag_seconds` | gauge | |
| `shoal_member_chunks_total` | counter | `result` (`fetched`, `retried`, `rate_limited`, `timeout`, `disconnected`, `error`) |
| `shoal_rest_invalid_requests` | gauge | |
| `shoal_rest_rate_limited_total` | counter | `route`, `scope` |
| `shoal_rest_request_seconds` | histogram | `method`, `route` |
| `shoal_rest_requests_total` | counter | `method`, `route`, `status` |
| `shoal_rest_retries_total` | counter | `route`, `reason` |
| `shoal_voice_packets_dropped_total` | counter | `reason` (`behind`, `unsealed`, `undecrypted`) |
| `shoal_voice_reconnects_total` | counter | `mode` (`resume`, `rejoin`) |

Routes are labelled by template (`GET /channels/{channel_id}`), never by filled-in path, so the number
of series stays bounded however busy the bot is.

## Useful queries

```promql
# Requests per second by route
sum by (route) (rate(shoal_rest_requests_total[5m]))

# How close the bot is to Discord's invalid request ban (10,000 per 10 minutes)
shoal_rest_invalid_requests

# 95th percentile delay between a message being sent and the bot seeing it
histogram_quantile(0.95, sum by (le) (rate(shoal_gateway_event_delay_seconds_bucket[5m])))

# Shards not ready
count(shoal_gateway_shard_ready == 0)
```
