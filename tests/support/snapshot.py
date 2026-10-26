"""The snapshot the current format writes, kept so a later change that cannot read it fails a test.

    uv run python -m tests.support.snapshot

writes `tests/cache/fixtures/snapshot-<SNAPSHOT_FORMAT>.msgpack`. Run it only together with bumping
`SNAPSHOT_FORMAT`: a layout change that old snapshots cannot load must bump the format, so a
restart after the upgrade ignores them on purpose instead of failing to read them.
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from shoal.cache.defaults import SNAPSHOT_FORMAT
from shoal.cache.entry import Source
from shoal.cache.policy import CacheConfig, CachePolicy, EntityKind
from shoal.cache.store import CacheStore
from shoal.core.snowflake import Snowflake
from shoal.payloads.gateway_events import MessageCreate
from shoal.payloads.guild import GuildMember
from shoal.payloads.message import MessageFlags, MessageType
from shoal.payloads.user import User
from tests.support.fakes import FakeClock
from tests.support.models import decoded, member, user

FIXTURE = Path(__file__).parent.parent / "cache" / "fixtures" / f"snapshot-{SNAPSHOT_FORMAT}.msgpack"
"""The snapshot of the current format."""
GUILD = Snowflake(10)
PERSIST_MESSAGES = CacheConfig(policies={EntityKind.MESSAGE: CachePolicy(persist=True)})
"""Messages are not kept in snapshots by default; the fixture keeps one to check its fields."""


def message() -> MessageCreate:
    """A message sent in a guild, with what only `MESSAGE_CREATE` carries."""
    return MessageCreate(
        id=Snowflake(2),
        channel_id=Snowflake(3),
        author=decoded(user(1, "kept"), User),
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
        flags=MessageFlags(),
        guild_id=GUILD,
        member=decoded(member(1, "kept"), GuildMember),
    )


async def write_fixture() -> None:
    """Write the fixture of the current format."""
    store = CacheStore(PERSIST_MESSAGES, clock=FakeClock())
    store.session_started(0)
    await store.put(store.users, Snowflake(1), message().author, Source.GATEWAY, shard=0)
    await store.put(store.messages, Snowflake(2), message(), Source.GATEWAY, scope=GUILD, shard=0)
    await store.save_snapshot(FIXTURE)


if __name__ == "__main__":
    asyncio.run(write_fixture())
