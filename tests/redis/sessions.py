from redis.asyncio import Redis

from shoal.gateway.session import GatewaySession
from shoal.redis.sessions import RedisSessionStore


def session(shard_id: int = 0, shard_count: int = 2) -> GatewaySession:
    return GatewaySession(
        shard_id=shard_id,
        shard_count=shard_count,
        session_id="abc",
        sequence=42,
        resume_gateway_url="wss://resume.discord.gg",
        saved_at=1_750_000_000.0,
    )


async def test_a_session_saved_by_one_process_is_resumed_by_another(redis: Redis, other: Redis) -> None:
    await RedisSessionStore(redis).save(session())
    assert await RedisSessionStore(other).load(0, 2) == session()
    assert await RedisSessionStore(other, prefix="another-bot").load(0, 2) is None


async def test_sessions_expire_and_can_be_forgotten(redis: Redis) -> None:
    store = RedisSessionStore(redis, max_age=60)
    await store.save(session())
    assert 59_000 < await redis.pttl("shoal:sessions:2:0") <= 60_000
    await store.delete(0, 2)
    assert await store.load(0, 2) is None


async def test_a_session_for_another_layout_or_corrupt_is_dropped(redis: Redis) -> None:
    store = RedisSessionStore(redis)
    await store.save(session())
    assert await store.load(0, 4) is None
    assert await redis.exists("shoal:sessions:2:0") == 1  # another count's session is left alone
    await redis.set("shoal:sessions:2:1", b"{not json")
    assert await store.load(1, 2) is None
    assert await redis.exists("shoal:sessions:2:1") == 0
