import logging
import stat
import sys
from collections.abc import Hashable
from datetime import UTC, datetime
from pathlib import Path
from typing import override

import msgspec
import pytest

from shoal.cache.collection import CacheCollection, CollectionFactory, MemoryCollections
from shoal.cache.defaults import SNAPSHOT_FORMAT
from shoal.cache.entry import Entry, Source
from shoal.cache.guild import CachedGuild
from shoal.cache.policy import CacheConfig, CachePolicy, EntityKind, RestartStrategy
from shoal.cache.store import CacheStore, Snapshot
from shoal.core.codec import decode_json
from shoal.core.metrics import CACHE_LOOKUPS, InMemoryMetrics
from shoal.core.snowflake import Snowflake
from shoal.payloads import Channel, ChannelType, GuildMember, GuildMemberFlags, MessageType, User
from shoal.payloads.gateway_events import GuildStickersUpdate, MessageCreate
from shoal.payloads.scheduled_event import GuildScheduledEvent
from shoal.payloads.soundboard import SoundboardSound
from shoal.payloads.stage_instance import StageInstance
from tests.support import snapshot
from tests.support.dispatches import DISPATCH_SAMPLES
from tests.support.fakes import FakeClock
from tests.support.models import decoded, guild_create

GUILD = Snowflake(10)
OTHER_GUILD = Snowflake(99)


def user(user_id: int, name: str = "u") -> User:
    return User(id=Snowflake(user_id), username=name, discriminator="0", global_name=None, avatar=None)


def cached_guild(guild_id: Snowflake) -> CachedGuild:
    return decoded(guild_create() | {"id": str(guild_id)}, CachedGuild)


def dm_channel(channel_id: int) -> Channel:
    return Channel(id=Snowflake(channel_id), type=ChannelType.DM)


def channel(channel_id: int, guild: Snowflake = GUILD) -> Channel:
    return Channel(id=Snowflake(channel_id), type=ChannelType.GUILD_TEXT, guild_id=guild)


def test_store_has_a_collection_and_snapshot_field_for_every_kind() -> None:
    store = CacheStore()
    assert store.kinds == set(EntityKind)
    marks = {"format", "saved_at", "revision", "shard_count", "shards"}
    snapshot_fields = set(Snapshot.__struct_fields__) - marks
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


async def test_forget_guild_removes_everything_scoped_to_it() -> None:
    store = CacheStore(clock=FakeClock())
    await store.put(store.guilds, GUILD, cached_guild(GUILD), Source.GATEWAY, scope=GUILD, shard=0)
    await store.put(store.channels, Snowflake(1), channel(1), Source.GATEWAY, scope=GUILD, shard=0)
    await store.put(store.users, Snowflake(5), user(5), Source.GATEWAY, shard=0)
    assert await store.forget_guild(GUILD) == 2
    assert await store.get_user(5) is not None


async def test_sweep_forgets_only_guilds_the_bot_left_while_offline() -> None:
    store = CacheStore(clock=FakeClock())
    store.session_started(0)
    for guild_id in (GUILD, OTHER_GUILD):
        await store.put(
            store.guilds, guild_id, cached_guild(guild_id), Source.GATEWAY, scope=guild_id, shard=0
        )
        await store.put(
            store.channels,
            Snowflake(guild_id + 1),
            channel(guild_id + 1, guild_id),
            Source.GATEWAY,
            scope=guild_id,
            shard=0,
        )
    await store.put(store.members, (GUILD, Snowflake(7)), _member(), Source.GATEWAY, scope=GUILD, shard=0)
    await store.put(store.users, Snowflake(7), user(7), Source.GATEWAY, shard=0)
    await store.put(store.channels, Snowflake(98), dm_channel(98), Source.GATEWAY, shard=0)
    store.session_started(0)
    # Only GUILD came back; a large guild's members and every user and DM were not resent.
    await store.put(store.guilds, GUILD, cached_guild(GUILD), Source.GATEWAY, scope=GUILD, shard=0)
    assert await store.sweep_stale() == 2
    assert await store.get_guild(OTHER_GUILD) is None
    assert await store.get_channel(OTHER_GUILD + 1) is None
    assert await store.get_guild(GUILD) is not None
    assert await store.get_channel(GUILD + 1) is not None
    assert await store.get_member(GUILD, 7) is not None
    assert await store.get_user(7) is not None
    assert await store.get_channel(98) is not None


async def test_sweep_keeps_unavailable_guilds_and_shards_without_a_session() -> None:
    store = CacheStore(clock=FakeClock())
    store.session_started(0)
    await store.put(store.guilds, GUILD, cached_guild(GUILD), Source.GATEWAY, scope=GUILD, shard=0)
    await store.put(
        store.guilds, OTHER_GUILD, cached_guild(OTHER_GUILD), Source.GATEWAY, scope=OTHER_GUILD, shard=7
    )
    store.session_started(0)
    store.mark_unavailable(GUILD)
    assert await store.sweep_stale() == 0
    assert await store.get_guild(GUILD) is not None
    assert await store.get_guild(OTHER_GUILD) is not None
    store.mark_available(GUILD)
    assert await store.sweep_stale() == 1
    assert await store.get_guild(GUILD) is None


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
    assert await restored.sweep_stale() == 0
    assert await restored.get_user(1) is not None


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


async def test_a_snapshot_from_another_shard_count_is_not_restored(tmp_path: Path) -> None:
    path = tmp_path / "snapshot"
    await CacheStore().save_snapshot(path, shard_count=8)
    assert not await CacheStore().load_snapshot(path, shard_count=16)
    assert await CacheStore().load_snapshot(path, shard_count=8)
    # Either side unknown: nothing to compare, so it loads.
    assert await CacheStore().load_snapshot(path)
    await CacheStore().save_snapshot(path)
    assert await CacheStore().load_snapshot(path, shard_count=16)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
async def test_snapshots_are_owner_only(tmp_path: Path) -> None:
    path = await snapshot_of_shard_zero(tmp_path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def _member() -> GuildMember:
    return GuildMember(roles=[], joined_at=None, deaf=False, mute=False, flags=GuildMemberFlags())


def _message() -> MessageCreate:
    return MessageCreate(
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


async def test_peek_reads_synchronously_and_counts_like_value() -> None:
    metrics = InMemoryMetrics()
    store = CacheStore(clock=FakeClock(), metrics=metrics)
    store.session_started(0)
    await store.put(store.channels, Snowflake(1), channel(1), Source.GATEWAY, scope=GUILD, shard=0)
    await store.put(store.channels, Snowflake(2), channel(2, OTHER_GUILD), Source.GATEWAY, scope=OTHER_GUILD)
    assert store.peek(store.channels, Snowflake(1)) == channel(1)
    assert store.peek(store.channels, Snowflake(3)) is None
    assert store.peek_scoped(store.channels, GUILD) == [channel(1)]
    store.session_started(0)
    assert store.peek(store.channels, Snowflake(1), fresh_only=True) is None
    assert store.peek_scoped(store.channels, GUILD, fresh_only=True) == []
    assert store.peek_scoped(store.channels, OTHER_GUILD, fresh_only=True) == [channel(2, OTHER_GUILD)]
    counts = {key[1]: value for key, value in metrics.counters.items() if key[0] == CACHE_LOOKUPS.name}
    assert counts == {
        (("kind", "channel"), ("result", "hit")): 1,
        (("kind", "channel"), ("result", "miss")): 1,
        (("kind", "channel"), ("result", "stale")): 1,
    }


async def test_the_newer_kinds_survive_a_snapshot(tmp_path: Path) -> None:
    def sample[T](name: str, kind: type[T]) -> T:
        return decode_json(msgspec.json.encode(DISPATCH_SAMPLES[name]), kind)

    store = CacheStore(clock=FakeClock())
    sticker = sample("GUILD_STICKERS_UPDATE", GuildStickersUpdate).stickers[0]
    stage = sample("STAGE_INSTANCE_CREATE", StageInstance)
    scheduled = sample("GUILD_SCHEDULED_EVENT_CREATE", GuildScheduledEvent)
    sound = sample("GUILD_SOUNDBOARD_SOUND_CREATE", SoundboardSound)
    await store.put(store.stickers, sticker.id, sticker, Source.GATEWAY, scope=GUILD)
    await store.put(store.stage_instances, stage.id, stage, Source.GATEWAY, scope=GUILD)
    await store.put(store.scheduled_events, scheduled.id, scheduled, Source.GATEWAY, scope=GUILD)
    await store.put(store.soundboard_sounds, sound.sound_id, sound, Source.GATEWAY, scope=GUILD)
    path = tmp_path / "snapshot"
    await store.save_snapshot(path)
    restored = CacheStore(clock=FakeClock())
    assert await restored.load_snapshot(path)
    assert await restored.get_sticker(sticker.id) == sticker
    assert await restored.get_stage_instance(stage.id) == stage
    assert await restored.get_scheduled_event(scheduled.id) == scheduled
    assert await restored.get_soundboard_sound(sound.sound_id) == sound


async def test_the_snapshot_this_format_wrote_still_loads() -> None:
    # A change that cannot read it must bump SNAPSHOT_FORMAT and write a new one (tests/support/snapshot.py).
    assert snapshot.FIXTURE.exists(), f"no fixture for snapshot format {SNAPSHOT_FORMAT}"
    restored = CacheStore(snapshot.PERSIST_MESSAGES, clock=FakeClock())
    assert await restored.load_snapshot(snapshot.FIXTURE)
    assert await restored.get_user(1) is not None
    kept = await restored.get_message(2)
    # What only MESSAGE_CREATE carries survives the snapshot.
    assert kept is not None
    assert (kept.guild_id, kept.content) == (snapshot.GUILD, "hi")
    assert not isinstance(kept.member, msgspec.UnsetType)


async def test_a_detached_guild_is_a_copy_of_only_that_guild() -> None:
    store = CacheStore(clock=FakeClock())
    await store.put(store.guilds, GUILD, cached_guild(GUILD), Source.GATEWAY, scope=GUILD, shard=0)
    await store.put(store.channels, Snowflake(1), channel(1), Source.GATEWAY, scope=GUILD, shard=0)
    await store.put(
        store.channels, Snowflake(2), channel(2, OTHER_GUILD), Source.GATEWAY, scope=OTHER_GUILD, shard=0
    )
    detached = await store.detached_guild(GUILD)
    await store.forget_guild(GUILD)
    assert await detached.get_guild(GUILD) is not None
    assert await detached.get_channel(1) is not None
    assert await detached.get_channel(2) is None
    assert await store.get_channel(1) is None


async def test_after_a_reshard_old_shard_numbers_neither_stale_nor_sweep_entries() -> None:
    store = CacheStore(clock=FakeClock())
    store.session_started(0)
    for guild_id in (GUILD, OTHER_GUILD):
        await store.put(
            store.guilds, guild_id, cached_guild(guild_id), Source.GATEWAY, scope=guild_id, shard=0
        )
    store.resharded()
    # Under the new count, shard 0 receives only GUILD; OTHER_GUILD moved to another shard.
    store.session_started(0)
    await store.put(store.guilds, GUILD, cached_guild(GUILD), Source.GATEWAY, scope=GUILD, shard=0)
    assert await store.sweep_stale() == 0
    assert await store.get_guild(OTHER_GUILD, fresh_only=True) is not None


class _Shared(CollectionFactory):
    """Memory collections that pretend to be shared with other processes."""

    def __init__(self, clock: FakeClock) -> None:
        self.memory = MemoryCollections(clock)

    @property
    @override
    def shared(self) -> bool:
        return True

    @override
    def __call__[K: Hashable, V](
        self, kind: EntityKind, policy: CachePolicy, key: type[K], entry: type[Entry[V]]
    ) -> CacheCollection[K, V]:
        return self.memory(kind, policy, key, entry)


async def test_a_shared_store_numbers_on_from_the_clock_and_keeps_no_snapshots(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = FakeClock()
    shared = CacheStore(clock=clock, collections=_Shared(clock))
    assert shared.revision == round(clock.wall() * 1_000_000)
    assert not MemoryCollections(clock).shared
    path = tmp_path / "cache.snapshot"
    with caplog.at_level(logging.WARNING, logger="shoal.cache"):
        await shared.save_snapshot(path)
        assert not path.exists()
        await CacheStore(clock=clock).save_snapshot(path)
        assert not await shared.load_snapshot(path)
    assert "not saving a cache snapshot" in caplog.text
    assert "not loading a cache snapshot" in caplog.text
