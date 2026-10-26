import pytest

from shoal.core.cooldown import Cooldown, DynamicCooldown
from shoal.core.defaults import COOLDOWN_PRUNE_ABOVE, COOLDOWN_PRUNE_INTERVAL
from tests.support.fakes import ManualClock


def by_name(name: str) -> str:
    return name


async def test_a_cooldown_refuses_until_its_window_passes() -> None:
    clock = ManualClock()
    cooldown = Cooldown[str](2, 10.0, key=by_name, clock=clock)
    assert cooldown.update_rate_limit("ada") == 0.0
    await clock.advance(4.0)
    assert cooldown.update_rate_limit("ada") == 0.0
    assert cooldown.update_rate_limit("ada") == 6.0
    assert cooldown.update_rate_limit("grace") == 0.0
    await clock.advance(6.5)
    assert cooldown.update_rate_limit("ada") == 0.0


async def test_asking_how_long_to_wait_records_nothing() -> None:
    clock = ManualClock()
    cooldown = Cooldown[str](3, 10.0, key=by_name, clock=clock)
    cooldown.update_rate_limit("ada")
    cooldown.update_rate_limit("ada")
    assert cooldown.get_retry_after("ada") == 0.0
    assert cooldown.get_retry_after("ada") == 0.0
    assert cooldown.update_rate_limit("ada") == 0.0
    await clock.advance(2.0)
    assert cooldown.get_retry_after("ada") == 8.0
    assert cooldown.get_retry_after("grace") == 0.0
    assert cooldown.tracked == 1


def test_a_cooldown_can_be_reset() -> None:
    cooldown = Cooldown[str](1, 60.0, key=by_name, clock=ManualClock())
    cooldown.update_rate_limit("ada")
    assert cooldown.update_rate_limit("ada") > 0
    cooldown.reset("ada")
    assert cooldown.update_rate_limit("ada") == 0.0


def test_a_cooldown_needs_a_positive_rate_and_window() -> None:
    with pytest.raises(ValueError, match="rate >= 1"):
        Cooldown[str](0, 1.0, key=by_name)
    with pytest.raises(ValueError, match="per > 0"):
        Cooldown[str](1, 0.0, key=by_name)


async def test_a_busy_cooldown_forgets_expired_keys_once_per_window() -> None:
    clock = ManualClock()
    cooldown = Cooldown[str](1, 1.0, key=by_name, clock=clock)
    await clock.advance(1.0)
    for index in range(COOLDOWN_PRUNE_ABOVE + 1):
        cooldown.update_rate_limit(str(index))
    assert cooldown.tracked == COOLDOWN_PRUNE_ABOVE + 1
    await clock.advance(1.0)
    cooldown.update_rate_limit("again")
    assert cooldown.tracked == 1
    cooldown.update_rate_limit("soon")
    assert cooldown.tracked == 2


async def test_a_long_window_is_still_pruned_regularly() -> None:
    clock = ManualClock()
    day = 86_400.0
    cooldown = Cooldown[str](1, day, key=by_name, clock=clock)
    for index in range(COOLDOWN_PRUNE_ABOVE + 1):
        cooldown.update_rate_limit(str(index))
    # A day later every key has expired; they go at the next scan, not a whole window after the last.
    await clock.advance(day)
    cooldown.update_rate_limit("new")
    assert cooldown.tracked == 1
    for index in range(COOLDOWN_PRUNE_ABOVE + 1):
        cooldown.update_rate_limit(f"more {index}")
    await clock.advance(COOLDOWN_PRUNE_INTERVAL)
    cooldown.update_rate_limit("late")
    assert cooldown.tracked == COOLDOWN_PRUNE_ABOVE + 3


def per_name(name: str) -> Cooldown[str] | None:
    return None if name == "vip" else Cooldown(1, 10.0 if name.startswith("slow") else 2.0)


async def test_a_dynamic_cooldown_takes_each_keys_limit_from_its_first_use() -> None:
    clock = ManualClock()
    cooldown = DynamicCooldown[str](per_name, key=by_name, clock=clock)
    assert cooldown.update_rate_limit("ada") == 0.0
    assert cooldown.update_rate_limit("ada") == 2.0
    assert cooldown.update_rate_limit("slowpoke") == 0.0
    assert cooldown.update_rate_limit("slowpoke") == 10.0
    assert cooldown.get_retry_after("slowpoke") == 10.0
    for _ in range(5):
        assert cooldown.update_rate_limit("vip") == 0.0
    assert cooldown.get_retry_after("vip") == 0.0
    assert cooldown.tracked == 2
    cooldown.reset("ada")
    assert cooldown.update_rate_limit("ada") == 0.0


async def test_without_a_key_every_subject_shares_one_count() -> None:
    clock = ManualClock()
    shared = Cooldown[str](1, 5.0, clock=clock)
    assert shared.update_rate_limit("ada") == 0.0
    assert shared.update_rate_limit("grace") == 5.0
    dynamic = DynamicCooldown[str](lambda _: Cooldown(1, 5.0), clock=clock)
    assert dynamic.update_rate_limit("ada") == 0.0
    assert dynamic.update_rate_limit("grace") == 5.0


async def test_a_busy_dynamic_cooldown_forgets_idle_keys() -> None:
    clock = ManualClock()
    cooldown = DynamicCooldown[str](lambda _: Cooldown(1, 1.0), key=by_name, clock=clock)
    await clock.advance(COOLDOWN_PRUNE_INTERVAL)
    for index in range(COOLDOWN_PRUNE_ABOVE + 1):
        cooldown.update_rate_limit(str(index))
    await clock.advance(COOLDOWN_PRUNE_INTERVAL)
    cooldown.update_rate_limit("fresh")
    assert cooldown.tracked == 1
