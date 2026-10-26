import fakeredis
import pytest
from redis.asyncio import Redis

from shoal.cache.collection import MemoryCollection
from shoal.cache.entry import Entry, Freshness, Source
from shoal.cache.store import CacheStore
from shoal.core.snowflake import Snowflake
from shoal.payloads import GuildMember, GuildMemberFlags, User
from shoal.redis.cache import RedisCollection, RedisCollections
from tests.support.fakes import FakeClock
from tests.support.redis import keys_of

GUILD = Snowflake(10)


def user(user_id: int, name: str = "u") -> User:
    return User(id=Snowflake(user_id), username=name, discriminator="0", global_name=None, avatar=None)


def entry(value: str, scope: Snowflake | None = None) -> Entry[str]:
    return Entry(
        value=value,
        freshness=Freshness(source=Source.GATEWAY, observed_at=0.0, revision=1),
        scope=scope,
    )


def collection(
    redis: Redis, *, ttl: float | None = None, max_entries: int | None = None
) -> RedisCollection[int, str]:
    return RedisCollection[int, str](
        redis,
        name="test",
        key_type=int,
        entry_type=Entry[str],
        ttl=ttl,
        local=MemoryCollection[int, str](FakeClock(), max_entries=max_entries),
    )


async def test_what_one_store_writes_another_reads(redis: Redis, other: Redis) -> None:
    clock = FakeClock()
    first = CacheStore(clock=clock, collections=RedisCollections(redis, clock=clock))
    second = CacheStore(clock=clock, collections=RedisCollections(other, clock=clock))
    await first.put(first.users, Snowflake(1), user(1, "ann"), Source.GATEWAY)
    assert second.peek(second.users, Snowflake(1)) is None  # not read here yet
    found = await second.get_user(1)
    assert found is not None
    assert found.username == "ann"
    assert second.peek(second.users, Snowflake(1)) == found
    member = GuildMember(
        user=user(2), roles=[], joined_at=None, deaf=False, mute=False, flags=GuildMemberFlags()
    )
    await first.put(first.members, (GUILD, Snowflake(2)), member, Source.GATEWAY, scope=GUILD)
    assert [key for key, _ in await second.members.scoped(GUILD)] == [(GUILD, Snowflake(2))]


async def test_entries_are_read_written_and_deleted(redis: Redis) -> None:
    stored = collection(redis)
    await stored.set(1, entry("a", GUILD))
    await stored.set(2, entry("b"))
    assert await stored.size() == 2
    assert sorted(key for key, _ in await stored.items()) == [1, 2]
    assert [key for key, _ in await stored.scoped(GUILD)] == [1]
    assert [key for key, _ in await stored.scoped(None)] == [2]
    assert [key for key, _ in stored.peek_scoped(GUILD)] == [1]
    assert sorted(key for key, _ in stored.peek_items()) == [1, 2]
    deleted = await stored.delete(1)
    assert deleted is not None
    assert deleted.value == "a"
    assert await stored.delete(1) is None
    assert stored.peek(1) is None
    assert await stored.scoped(GUILD) == []
    await stored.clear()
    assert await stored.size() == 0
    assert stored.peek_items() == []
    assert await keys_of(redis) == []


async def test_an_entry_moved_or_gone_is_dropped_from_the_indexes(redis: Redis, other: Redis) -> None:
    stored, elsewhere = collection(redis), collection(other)
    await stored.set(1, entry("a", GUILD))
    await stored.set(2, entry("b", GUILD))
    await elsewhere.set(1, entry("a", Snowflake(99)))  # moved to another guild by another process
    await redis.delete("shoal:cache:test:entry:2")  # evicted
    assert await stored.scoped(GUILD) == []
    assert await redis.zcard("shoal:cache:test:scope:10") == 0
    assert [key for key, _ in await stored.items()] == [1]
    assert await stored.get(2) is None
    assert stored.peek(2) is None


async def test_entries_expire_as_their_policy_says(redis: Redis) -> None:
    stored = collection(redis, ttl=30)
    await stored.set(1, entry("a"))
    assert 29_000 < await redis.pttl("shoal:cache:test:entry:1") <= 30_000
    await collection(redis).set(2, entry("b"))
    assert await redis.pttl("shoal:cache:test:entry:2") == -1


async def test_the_local_copy_is_bounded(redis: Redis) -> None:
    stored = collection(redis, max_entries=1)
    await stored.set(1, entry("a"))
    await stored.set(2, entry("b"))
    assert stored.peek(1) is None
    assert await stored.get(1) is not None  # Redis still has it
    assert stored.peek(1) is not None


async def test_an_expired_entry_leaves_its_indexes(redis: Redis) -> None:
    stored = collection(redis, ttl=30)
    await stored.set(1, entry("a", GUILD))
    await stored.set(2, entry("b", GUILD))
    # Entry 1 expires: Redis drops its key, and its index score is in the past.
    await redis.delete("shoal:cache:test:entry:1")
    await redis.zadd("shoal:cache:test:all", {"1": 1})
    assert await stored.size() == 1
    assert await redis.zcard("shoal:cache:test:all") == 1
    assert [key for key, _ in await stored.scoped(GUILD)] == [2]
    assert await redis.zcard("shoal:cache:test:scope:10") == 1


async def test_a_moved_or_deleted_entry_leaves_the_guild_it_was_in(redis: Redis) -> None:
    stored = collection(redis)
    await stored.set(1, entry("a", GUILD))
    await stored.set(1, entry("a", Snowflake(99)))
    assert await redis.zcard("shoal:cache:test:scope:10") == 0
    assert await redis.zcard("shoal:cache:test:scope:99") == 1
    await stored.delete(1)
    assert await redis.zcard("shoal:cache:test:scope:99") == 0
    assert await redis.zcard("shoal:cache:test:all") == 0
    assert await stored.delete(1) is None


async def test_more_entries_than_one_page_are_all_read(redis: Redis) -> None:
    stored = collection(redis)
    for key in range(1, 2_501):
        await stored.set(key, entry(str(key), GUILD))
    assert len(await stored.items()) == 2_500
    assert len(await stored.scoped(GUILD)) == 2_500
    await stored.clear()
    assert await keys_of(redis) == []


def test_a_client_that_decodes_responses_is_refused() -> None:
    decoding = fakeredis.FakeAsyncRedis(server=fakeredis.FakeServer(), decode_responses=True)
    with pytest.raises(ValueError, match="decode_responses"):
        RedisCollections(decoding)
