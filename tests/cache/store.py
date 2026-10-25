import stat
import sys
from datetime import UTC, datetime
from pathlib import Path

import msgspec
import pytest

from shoal.cache.defaults import SNAPSHOT_FORMAT
from shoal.cache.entry import Source
from shoal.cache.policy import CacheConfig, CachePolicy, EntityKind, RestartStrategy
from shoal.cache.store import CacheStore, Snapshot
from shoal.core.metrics import CACHE_LOOKUPS, InMemoryMetrics
from shoal.core.snowflake import Snowflake
from shoal.payloads import Channel, ChannelType, GuildMember, GuildMemberFlags, Message, MessageType, User
from tests.support.fakes import FakeClock

GUILD = Snowflake(10)
OTHER_GUILD = Snowflake(99)


def user(user_id: int, name: str = "u") -> User:
    return User(id=Snowflake(user_id), username=name, discriminator="0", global_name=None, avatar=None)


def channel(channel_id: int, guild: Snowflake = GUILD) -> Channel:
    return Channel(id=Snowflake(channel_id), type=ChannelType.GUILD_TEXT, guild_id=guild)


def test_store_has_a_collection_and_snapshot_field_for_every_kind() -> None:
    store = CacheStore()
    assert store.kinds == set(EntityKind)
    snapshot_fields = set(Snapshot.__struct_fields__) - {"format", "saved_at", "revision", "shards"}
    attributes = {kind: f"{kind.value}s" for kind in EntityKind}
    assert snapshot_fields == set(attributes.values())
    for name in attributes.values():
        assert hasattr(store, name)


async def test_reads_report_hits_stale_entries_and_misses() -> None:
    metrics = InMemoryMetrics()
    store = CacheStore(clock=FakeClock(), metrics=metrics)
    store.session_started(0)
    await store.put(store.users, Snowflake(1), user(1), Source.GATEWAY, shard=0)
    assert await store.get_user(1) == user(1)
    assert await store.get_user(2) is None
    store.session_started(0)
    assert await store.get_user(1) == user(1)
    assert await store.get_user(1, fresh_only=True) is None
    counts = {key[1]: value for key, value in metrics.counters.items() if key[0] == CACHE_LOOKUPS.name}
    assert counts == {
        (("kind", "user"), ("result", "hit")): 1,
        (("kind", "user"), ("result", "miss")): 1,
        (("kind", "user"), ("result", "stale")): 2,
    }


async def test_a_new_session_on_one_shard_leaves_other_shards_fresh() -> None:
    store = CacheStore(clock=FakeClock())
    store.session_started(0)
    store.session_started(1)
    await store.put(store.channels, Snowflake(1), channel(1), Source.GATEWAY, scope=GUILD, shard=0)
    await store.put(
        store.channels, Snowflake(2), channel(2, OTHER_GUILD), Source.GATEWAY, scope=OTHER_GUILD, shard=1
    )
    await store.put(store.users, Snowflake(3), user(3), Source.REST)
    store.session_started(0)
    assert await store.get_channel(1, fresh_only=True) is None
    assert await store.get_channel(2, fresh_only=True) is not None
    assert await store.get_user(3, fresh_only=True) is not None


async def test_edits_keep_the_entry_provenance() -> None:
    store = CacheStore(clock=FakeClock())
    store.session_started(0)
    await store.put(store.users, Snowflake(1), user(1), Source.GATEWAY, shard=0)
    store.session_started(0)

    def rename(value: User) -> User:
        return msgspec.structs.replace(value, username="renamed")

    assert await store.edit(store.users, Snowflake(1), rename)
    assert not await store.edit(store.users, Snowflake(2), rename)
    assert await store.get_user(1, fresh_only=True) is None
    assert await store.get_user(1) == user(1, "renamed")


async def test_disabled_kinds_store_nothing() -> None:
    store = CacheStore(CacheConfig(policies={EntityKind.USER: CachePolicy.disabled()}))
    await store.put(store.users, Snowflake(1), user(1), Source.REST)
    assert await store.get_user(1) is None
    assert await store.users.scoped(None) == []


async def test_policies_reach_the_collections() -> None:
    clock = FakeClock()
    policies = {EntityKind.USER: CachePolicy(max_entries=1), EntityKind.CHANNEL: CachePolicy(ttl=10)}
    store = CacheStore(CacheConfig(policies=policies), clock=clock)
    await store.put(store.users, Snowflake(1), user(1), Source.REST)
    await store.put(store.users, Snowflake(2), user(2), Source.REST)
    assert await store.get_user(1) is None
    await store.put(store.channels, Snowflake(1), channel(1), Source.REST, scope=GUILD)
    clock.advance(10)
    assert await store.get_channel(1) is None


async def test_reconcile_drops_what_the_guild_create_did_not_contain() -> None:
    store = CacheStore(clock=FakeClock())
    store.session_started(0)
    await store.put(store.channels, Snowflake(1), channel(1), Source.GATEWAY, scope=GUILD, shard=0)
    await store.put(store.channels, Snowflake(2), channel(2), Source.GATEWAY, scope=OTHER_GUILD, shard=0)
    await store.put(store.messages, Snowflake(5), _message(), Source.GATEWAY, scope=GUILD, shard=0)
    since = store.revision
    await store.put(store.channels, Snowflake(3), channel(3), Source.GATEWAY, scope=GUILD, shard=0)
    assert await store.reconcile_guild(GUILD, since=since) == 1
    assert await store.get_channel(1) is None
    assert await store.get_channel(2) is not None
    assert await store.get_channel(3) is not None
    assert await store.get_message(5) is not None


async def test_large_guilds_keep_members_during_reconcile() -> None:
    store = CacheStore(clock=FakeClock())
    await store.put(store.members, (GUILD, Snowflake(1)), _member(), Source.GATEWAY, scope=GUILD)
    since = store.revision
    await store.reconcile_guild(GUILD, since=since, members=False)
    assert await store.get_member(GUILD, 1) is not None
    await store.reconcile_guild(GUILD, since=since)
    assert await store.get_member(GUILD, 1) is None


async def test_forget_guild_and_sweep() -> None:
    store = CacheStore(clock=FakeClock())
    store.session_started(0)
    await store.put(store.channels, Snowflake(1), channel(1), Source.GATEWAY, scope=GUILD, shard=0)
    await store.put(store.users, Snowflake(5), user(5), Source.GATEWAY, shard=0)
    assert await store.forget_guild(GUILD) == 1
    store.session_started(0)
    assert await store.sweep_stale() == 1
    assert await store.get_user(5) is None


async def test_sweep_keeps_unavailable_guilds_and_shards_without_a_session() -> None:
    store = CacheStore(clock=FakeClock())
    store.session_started(0)
    await store.put(store.channels, Snowflake(1), channel(1), Source.GATEWAY, scope=GUILD, shard=0)
    await store.put(
        store.channels, Snowflake(2), channel(2, OTHER_GUILD), Source.GATEWAY, scope=OTHER_GUILD, shard=0
    )
    await store.put(store.channels, Snowflake(3), channel(3), Source.GATEWAY, scope=GUILD, shard=7)
    store.session_started(0)
    store.mark_unavailable(GUILD)
    assert await store.sweep_stale() == 1
    assert await store.get_channel(1) is not None
    assert await store.get_channel(2) is None
    assert await store.get_channel(3) is not None
    store.mark_available(GUILD)
    assert await store.sweep_stale() == 1


async def snapshot_of_shard_zero(tmp_path: Path, *, sequence: int = 41) -> Path:
    store = CacheStore(clock=FakeClock())
    store.session_started(0)
    store.observe(0, sequence)
    await store.put(store.users, Snowflake(1), user(1, "kept"), Source.GATEWAY, shard=0)
    await store.put(store.messages, Snowflake(2), _message(), Source.GATEWAY, shard=0)
    path = tmp_path / "cache" / "snapshot.msgpack"
    await store.save_snapshot(path)
    return path


async def test_a_resume_that_continues_the_snapshot_makes_it_fresh(tmp_path: Path) -> None:
    path = await snapshot_of_shard_zero(tmp_path)
    assert [file.name for file in path.parent.iterdir()] == ["snapshot.msgpack"]
    restored = CacheStore(clock=FakeClock())
    assert await restored.load_snapshot(path)
    entry = await restored.users.get(Snowflake(1))
    assert entry is not None
    assert entry.freshness.source is Source.SNAPSHOT
    assert await restored.get_user(1, fresh_only=True) is None
    assert await restored.get_message(2) is None
    restored.observe(0, 42)
    restored.session_resumed(0)
    assert await restored.get_user(1, fresh_only=True) == user(1, "kept")


async def test_a_resume_that_does_not_continue_the_snapshot_keeps_it_stale(tmp_path: Path) -> None:
    path = await snapshot_of_shard_zero(tmp_path)
    restored = CacheStore(clock=FakeClock())
    await restored.load_snapshot(path)
    restored.observe(0, 50)
    restored.session_resumed(0)
    assert await restored.get_user(1, fresh_only=True) is None
    await restored.put(restored.users, Snowflake(9), user(9), Source.GATEWAY, shard=0)
    assert await restored.get_user(9, fresh_only=True) is not None


async def test_a_resume_within_the_process_changes_nothing() -> None:
    store = CacheStore(clock=FakeClock())
    store.session_started(0)
    await store.put(store.users, Snowflake(1), user(1), Source.GATEWAY, shard=0)
    store.session_resumed(0)
    assert await store.get_user(1, fresh_only=True) is not None


async def test_a_snapshot_followed_by_a_new_session_stays_stale(tmp_path: Path) -> None:
    path = await snapshot_of_shard_zero(tmp_path)
    restored = CacheStore(clock=FakeClock())
    await restored.load_snapshot(path)
    restored.session_started(0)
    assert await restored.get_user(1, fresh_only=True) is None
    assert await restored.sweep_stale() == 1


async def test_a_second_snapshot_keeps_shards_that_have_not_come_back(tmp_path: Path) -> None:
    path = await snapshot_of_shard_zero(tmp_path)
    restored = CacheStore(clock=FakeClock())
    await restored.load_snapshot(path)
    await restored.save_snapshot(path)
    again = CacheStore(clock=FakeClock())
    await again.load_snapshot(path)
    again.observe(0, 42)
    again.session_resumed(0)
    assert await again.get_user(1, fresh_only=True) is not None


async def test_loading_replaces_the_cache_and_skips_kinds_no_longer_persisted(tmp_path: Path) -> None:
    path = await snapshot_of_shard_zero(tmp_path)
    store = CacheStore(CacheConfig(policies={EntityKind.USER: CachePolicy(persist=False)}), clock=FakeClock())
    await store.put(store.channels, Snowflake(1), channel(1), Source.REST, scope=GUILD)
    assert await store.load_snapshot(path)
    assert await store.get_channel(1) is None
    assert await store.get_user(1) is None


async def test_snapshots_are_skipped_when_cold_missing_corrupt_or_incompatible(tmp_path: Path) -> None:
    path = tmp_path / "snapshot"
    assert not await CacheStore().load_snapshot(path)
    path.write_bytes(b"\xc1 not msgpack")
    assert not await CacheStore().load_snapshot(path)
    path.write_bytes(msgspec.msgpack.encode({"format": SNAPSHOT_FORMAT + 1, "entries": "unknown layout"}))
    assert not await CacheStore().load_snapshot(path)
    await CacheStore().save_snapshot(path)
    assert not await CacheStore(CacheConfig(restart=RestartStrategy.COLD)).load_snapshot(path)
    assert await CacheStore().load_snapshot(path)
    unreadable = tmp_path / "directory"
    unreadable.mkdir()
    assert not await CacheStore().load_snapshot(unreadable)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
async def test_snapshots_are_owner_only(tmp_path: Path) -> None:
    path = await snapshot_of_shard_zero(tmp_path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def _member() -> GuildMember:
    return GuildMember(roles=[], joined_at=None, deaf=False, mute=False, flags=GuildMemberFlags())


def _message() -> Message:
    return Message(
        id=Snowflake(2),
        channel_id=Snowflake(3),
        author=user(1),
        content="hi",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        edited_timestamp=None,
        tts=False,
        mention_everyone=False,
        mentions=[],
        mention_roles=[],
        attachments=[],
        embeds=[],
        pinned=False,
        type=MessageType.DEFAULT,
    )
