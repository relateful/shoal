import pytest

from shoal.cache.defaults import MESSAGE_CACHE_LIMIT
from shoal.cache.policy import DEFAULT_POLICIES, CacheConfig, CachePolicy, EntityKind, RestartStrategy


def test_every_kind_has_a_default_policy() -> None:
    assert set(DEFAULT_POLICIES) == set(EntityKind)


def test_defaults_bound_and_skip_volatile_kinds() -> None:
    assert DEFAULT_POLICIES[EntityKind.MESSAGE].max_entries == MESSAGE_CACHE_LIMIT
    assert not DEFAULT_POLICIES[EntityKind.MESSAGE].persist
    assert not DEFAULT_POLICIES[EntityKind.PRESENCE].persist
    assert DEFAULT_POLICIES[EntityKind.GUILD].persist


def test_config_overrides_one_kind_and_keeps_the_rest() -> None:
    config = CacheConfig(policies={EntityKind.MEMBER: CachePolicy.disabled()}, restart=RestartStrategy.COLD)
    assert not config.policy(EntityKind.MEMBER).enabled
    assert config.policy(EntityKind.GUILD) == DEFAULT_POLICIES[EntityKind.GUILD]
    assert CacheConfig().restart is RestartStrategy.WARM


def test_policy_validates_bounds() -> None:
    with pytest.raises(ValueError, match="max_entries"):
        CachePolicy(max_entries=0)
    with pytest.raises(ValueError, match="ttl"):
        CachePolicy(ttl=0)
