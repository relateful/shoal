import pytest

from shoal.gateway.ratelimit import GatewaySendLimiter
from shoal.payloads import GATEWAY_SEND_LIMIT
from tests.support.fakes import FakeClock


async def test_send_limiter_reserves_slots_for_heartbeats() -> None:
    clock = FakeClock()
    limiter = GatewaySendLimiter(clock, reserved=5)
    for _ in range(GATEWAY_SEND_LIMIT - 5):
        await limiter.acquire()
    started = clock.monotonic()
    for _ in range(5):
        await limiter.acquire(priority=True)
    assert clock.monotonic() == started
    await limiter.acquire()
    assert clock.monotonic() - started >= 60.0
    with pytest.raises(ValueError, match="reserved"):
        GatewaySendLimiter(clock, reserved=GATEWAY_SEND_LIMIT)
