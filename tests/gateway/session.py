import stat
import sys
from pathlib import Path

import pytest

from shoal.gateway.session import FileSessionStore, GatewaySession, MemorySessionStore
from tests.support.fakes import FakeClock


def session(shard_id: int = 0, *, saved_at: float = 1_750_000_000.0) -> GatewaySession:
    return GatewaySession(
        shard_id=shard_id,
        shard_count=2,
        session_id="abc",
        sequence=42,
        resume_gateway_url="wss://resume",
        saved_at=saved_at,
    )


async def test_memory_session_store() -> None:
    store = MemorySessionStore()
    await store.save(session())
    assert await store.load(0, 2) == session()
    assert await store.load(0, 3) is None
    await store.delete(0)
    assert await store.load(0, 2) is None


async def test_file_session_store_round_trips_and_expires(tmp_path: Path) -> None:
    clock = FakeClock()
    store = FileSessionStore(tmp_path / "sessions", max_age=60, clock=clock)
    await store.save(session(saved_at=clock.wall()))
    assert await store.load(0, 2) == session(saved_at=clock.wall())
    assert not list((tmp_path / "sessions").glob("*.tmp"))
    assert await store.load(0, 3) is None
    assert not (tmp_path / "sessions" / "shard-0.json").exists()
    await store.save(session(saved_at=clock.wall()))
    clock.advance(61)
    assert await store.load(0, 2) is None
    assert await store.load(1, 2) is None


async def test_file_session_store_discards_corrupt_files(tmp_path: Path) -> None:
    store = FileSessionStore(tmp_path)
    (tmp_path / "shard-0.json").write_bytes(b"{not json")
    assert await store.load(0, 2) is None
    assert not (tmp_path / "shard-0.json").exists()


async def test_file_session_store_rejects_sessions_dated_in_the_future(tmp_path: Path) -> None:
    clock = FakeClock()
    store = FileSessionStore(tmp_path, clock=clock)
    await store.save(session(saved_at=clock.wall() + 3600))
    assert await store.load(0, 2) is None


async def test_file_session_store_treats_an_unreadable_file_as_missing(tmp_path: Path) -> None:
    (tmp_path / "shard-0.json").mkdir()
    assert await FileSessionStore(tmp_path).load(0, 2) is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
async def test_file_session_store_writes_owner_only_files(tmp_path: Path) -> None:
    clock = FakeClock()
    await FileSessionStore(tmp_path / "sessions", clock=clock).save(session(saved_at=clock.wall()))
    mode = (tmp_path / "sessions" / "shard-0.json").stat().st_mode
    assert stat.S_IMODE(mode) == 0o600
