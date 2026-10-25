import pytest

from shoal.gateway.heartbeat import HeartbeatMonitor


def test_heartbeat_monitor_tracks_acks_and_latency() -> None:
    monitor = HeartbeatMonitor(41_250)
    assert monitor.interval == 41.25
    assert monitor.first_delay(0.5) == pytest.approx(20.625)
    assert not monitor.is_zombie()
    monitor.sent(10.0)
    assert monitor.is_zombie()
    monitor.acknowledged(10.25)
    assert not monitor.is_zombie()
    assert monitor.latency == pytest.approx(0.25)
    with pytest.raises(ValueError, match="jitter"):
        monitor.first_delay(1.0)
    with pytest.raises(ValueError, match="positive"):
        HeartbeatMonitor(0)


def test_an_ack_with_nothing_pending_does_not_measure_latency() -> None:
    monitor = HeartbeatMonitor(40_000)
    monitor.sent(10.0)
    monitor.acknowledged(10.5)
    monitor.acknowledged(30.0)
    assert monitor.latency == pytest.approx(0.5)
