from shoal.cache.collection import MemoryCollection, NullCollection
from shoal.cache.entry import Entry, Freshness, Source
from shoal.core.snowflake import Snowflake
from tests.support.fakes import FakeClock


def entry(value: str, observed_at: float, scope: int | None = None) -> Entry[str]:
    return Entry(
        value=value,
        freshness=Freshness(source=Source.GATEWAY, observed_at=observed_at, revision=1),
        scope=None if scope is None else Snowflake(scope),
    )


async def test_memory_collection_evicts_the_least_recently_used() -> None:
    clock = FakeClock()
    collection = MemoryCollection[int, str](clock, max_entries=2)
    await collection.set(1, entry("a", clock.wall()))
    await collection.set(2, entry("b", clock.wall()))
    assert await collection.get(1) is not None
    await collection.set(3, entry("c", clock.wall()))
    assert await collection.get(2) is None
    assert await collection.size() == 2
    assert [key for key, _ in await collection.items()] == [1, 3]


async def test_memory_collection_expires_by_observation_time() -> None:
    clock = FakeClock()
    collection = MemoryCollection[int, str](clock, ttl=10)
    await collection.set(1, entry("old", clock.wall() - 11))
    await collection.set(2, entry("new", clock.wall()))
    assert await collection.get(1) is None
    assert [key for key, _ in await collection.items()] == [2]
    clock.advance(10)
    assert await collection.items() == []


async def test_memory_collection_delete_and_clear() -> None:
    clock = FakeClock()
    collection = MemoryCollection[int, str](clock)
    await collection.set(1, entry("a", clock.wall()))
    removed = await collection.delete(1)
    assert removed is not None
    assert removed.value == "a"
    assert await collection.delete(1) is None
    await collection.set(2, entry("b", clock.wall()))
    await collection.clear()
    assert await collection.size() == 0


async def test_memory_collection_indexes_entries_by_scope() -> None:
    clock = FakeClock()
    collection = MemoryCollection[int, str](clock, max_entries=3, ttl=10)
    await collection.set(1, entry("a", clock.wall(), scope=5))
    await collection.set(2, entry("b", clock.wall(), scope=5))
    await collection.set(3, entry("c", clock.wall()))
    assert sorted(key for key, _ in await collection.scoped(Snowflake(5))) == [1, 2]
    assert [key for key, _ in await collection.scoped(None)] == [3]
    await collection.set(2, entry("moved", clock.wall(), scope=6))
    assert [key for key, _ in await collection.scoped(Snowflake(5))] == [1]
    assert [key for key, _ in await collection.scoped(Snowflake(6))] == [2]
    await collection.set(4, entry("d", clock.wall(), scope=5))
    assert [key for key, _ in await collection.scoped(Snowflake(5))] == [4]
    await collection.set(5, entry("old", clock.wall() - 11, scope=7))
    assert await collection.scoped(Snowflake(7)) == []
    assert await collection.size() == 2
    await collection.clear()
    assert await collection.scoped(Snowflake(6)) == []


async def test_null_collection_stores_nothing() -> None:
    collection = NullCollection[int, str]()
    await collection.set(1, entry("a", 0))
    assert await collection.get(1) is None
    assert await collection.delete(1) is None
    assert await collection.items() == []
    assert await collection.scoped(None) == []
    assert await collection.size() == 0
    await collection.clear()


async def test_memory_collection_peeks_synchronously_with_the_same_rules() -> None:
    clock = FakeClock()
    collection = MemoryCollection[int, str](clock, ttl=10)
    await collection.set(1, entry("a", clock.wall(), scope=5))
    await collection.set(2, entry("old", clock.wall() - 11))
    peeked = collection.peek(1)
    assert peeked is not None
    assert peeked.value == "a"
    assert collection.peek(2) is None  # expired, and removed on the way
    assert [key for key, _ in collection.peek_scoped(Snowflake(5))] == [1]
    assert collection.peek_scoped(None) == []
    assert [key for key, _ in collection.peek_items()] == [1]
    assert await collection.size() == 1


async def test_peeks_see_what_the_async_api_wrote() -> None:
    clock = FakeClock()
    collection = MemoryCollection[int, str](clock, max_entries=2)
    await collection.set(1, entry("a", clock.wall(), scope=5))
    await collection.set(2, entry("b", clock.wall()))
    assert collection.peek(1) is not None  # 1 is now the most recently used
    await collection.set(3, entry("c", clock.wall()))
    assert collection.peek(2) is None
    assert sorted(key for key, _ in collection.peek_items()) == [1, 3]


def test_null_collection_peeks_nothing() -> None:
    collection = NullCollection[int, str]()
    assert collection.peek(1) is None
    assert collection.peek_scoped(None) == []
    assert collection.peek_items() == []
