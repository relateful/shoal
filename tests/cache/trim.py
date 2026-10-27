from pathlib import Path

import msgspec
import pytest

from shoal.cache.entry import Source
from shoal.cache.policy import CacheConfig, CachePolicy, EntityKind
from shoal.cache.store import CacheStore
from shoal.cache.trim import FieldTrim
from shoal.core.snowflake import Snowflake
from shoal.payloads import Channel, ChannelType, User
from tests.support.fakes import FakeClock

GUILD = Snowflake(10)


def channel(channel_id: int = 1) -> Channel:
    return Channel(
        id=Snowflake(channel_id),
        type=ChannelType.GUILD_TEXT,
        guild_id=GUILD,
        name="general",
        topic="chat",
        position=3,
        nsfw=True,
    )


def trimmed_store(*fields: str) -> CacheStore:
    policy = CachePolicy(fields=frozenset(fields))
    return CacheStore(CacheConfig(policies={EntityKind.CHANNEL: policy}), clock=FakeClock())


def test_fields_not_kept_are_reset_and_identity_stays() -> None:
    trim = FieldTrim(EntityKind.CHANNEL, Channel, {"name"})
    kept = trim(channel())
    assert (kept.id, kept.type, kept.guild_id, kept.name) == (1, ChannelType.GUILD_TEXT, GUILD, "general")
    defaults = Channel(id=Snowflake(1), type=ChannelType.GUILD_TEXT)
    assert (kept.topic, kept.position, kept.nsfw) == (defaults.topic, defaults.position, defaults.nsfw)


class Listed(msgspec.Struct):
    id: int
    items: list[int] = msgspec.field(default_factory=list[int])


def test_default_factories_give_each_value_its_own() -> None:
    trim = FieldTrim(EntityKind.CHANNEL, Listed, ())
    first, second = trim(Listed(1, [1])), trim(Listed(2, [2]))
    assert (first.items, second.items) == ([], [])
    assert first.items is not second.items


def test_an_unknown_field_fails_when_the_store_is_created() -> None:
    with pytest.raises(ValueError, match="channel is cached as Channel, which has no field nope, tpoic"):
        _ = trimmed_store("name", "tpoic", "nope")


def test_keeping_everything_changes_nothing() -> None:
    every = {field.name for field in msgspec.structs.fields(Channel)}
    value = channel()
    assert FieldTrim(EntityKind.CHANNEL, Channel, every)(value) is value


async def test_puts_and_edits_store_only_the_kept_fields() -> None:
    store = trimmed_store("name")
    await store.put(store.channels, Snowflake(1), channel(), Source.GATEWAY, scope=GUILD)
    cached = await store.get_channel(1)
    assert cached is not None
    assert (cached.name, cached.topic) == ("general", msgspec.UNSET)

    def retopic(value: Channel) -> Channel:
        return msgspec.structs.replace(value, topic="new", name="renamed")

    assert await store.edit(store.channels, Snowflake(1), retopic)
    cached = await store.get_channel(1)
    assert cached is not None
    assert (cached.name, cached.topic) == ("renamed", msgspec.UNSET)


async def test_other_kinds_are_untouched() -> None:
    store = trimmed_store("name")
    user = User(id=Snowflake(1), username="u", discriminator="0", global_name="Global", avatar=None)
    await store.put(store.users, Snowflake(1), user, Source.GATEWAY)
    assert await store.get_user(1) == user


async def test_a_snapshot_from_a_wider_policy_is_trimmed_on_load(tmp_path: Path) -> None:
    path = tmp_path / "cache.snapshot"
    full = CacheStore(clock=FakeClock())
    await full.put(full.channels, Snowflake(1), channel(), Source.GATEWAY, scope=GUILD)
    await full.save_snapshot(path)
    store = trimmed_store("topic")
    assert await store.load_snapshot(path)
    cached = await store.get_channel(1)
    assert cached is not None
    assert (cached.name, cached.topic, cached.guild_id) == (msgspec.UNSET, "chat", GUILD)
