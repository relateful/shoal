import asyncio
import logging
from collections.abc import Callable, Sequence
from typing import ClassVar, override

import msgspec
import pytest

from shoal.client import client as client_module
from shoal.client.client import Client, ClientError, Listener
from shoal.client.interaction import Interaction
from shoal.core.dispatch import DispatchEvent, DispatchHandler
from shoal.models.activity import Game
from shoal.models.channel import PartialMessageable, TextChannel
from shoal.payloads import ActivityType, Intents, StatusType, UpdatePresence
from shoal.rest.client import RestClient, Token
from tests.support.calls import call_unchecked
from tests.support.client import INTENTS, Recorder, feed, logged_in, started
from tests.support.interactions import PersistentView, command
from tests.support.models import ALICE, APPLICATION, BOT, EMOJI, GENERAL, GUILD, channel, guild_create, user


async def test_login_learns_who_the_bot_is() -> None:
    client, transport = await logged_in()
    assert client.user is not None
    assert client.user.id == BOT
    assert client.application_id == APPLICATION
    assert [request.url.rsplit("/v10", 1)[1] for request in transport.requests] == [
        "/users/@me",
        "/applications/@me",
    ]


async def test_setup_hook_runs_after_login() -> None:
    class Bot(Client):
        hooked = False

        @override
        async def setup_hook(self) -> None:
            self.hooked = self.user is not None

    bot, _ = await logged_in(Bot)
    assert bot.hooked


async def test_nothing_works_before_login() -> None:
    client = Client(intents=INTENTS)
    with pytest.raises(ClientError, match="not logged in"):
        _ = client.rest
    with pytest.raises(ClientError, match="login"):
        await client.feed(DispatchEvent(0, "MESSAGE_CREATE", None, msgspec.Raw(b"{}")))
    assert client.user is None
    assert client.application_id is None
    assert client.latency is None
    assert not client.is_ready()


async def test_event_replaces_and_listen_adds() -> None:
    client, _ = await logged_in()
    calls: list[str] = []

    def handler(label: str) -> Listener:
        async def on_thing(value: object) -> None:
            calls.append(f"{label} {value}")

        return on_thing

    client.event(handler("first"))
    second = client.event(handler("second"))

    @client.listen("thing")
    async def also(value: object) -> None:
        calls.append(f"listener {value}")

    client.dispatch("thing", 1)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert sorted(calls) == ["listener 1", "second 1"]
    client.remove_listener(second)
    client.remove_listener(also, "thing")
    client.dispatch("thing", 2)
    await asyncio.sleep(0)
    assert len(calls) == 2


async def test_handlers_must_be_named_coroutines() -> None:
    client = Client(intents=INTENTS)

    def not_async() -> None: ...

    async def wrong_name() -> None: ...

    with pytest.raises(TypeError, match="coroutine"):
        call_unchecked(client.event, not_async)
    with pytest.raises(TypeError, match="named after its event"):
        client.event(wrong_name)
    client.add_listener(wrong_name, "anything")


async def test_handler_errors_reach_on_error(caplog: pytest.LogCaptureFixture) -> None:
    client, _ = await logged_in()

    @client.event
    async def on_boom() -> None:
        msg = "boom"
        raise RuntimeError(msg)

    with caplog.at_level(logging.ERROR, logger="shoal.client"):
        client.dispatch("boom")
        for _ in range(5):
            await asyncio.sleep(0)
    assert "handler for boom raised" in caplog.text

    class Reporting(Client):
        @override
        async def on_error(self, event: str, error: Exception, /, *args: object) -> None:
            reported.append((event, str(error), args))

    reported: list[tuple[str, str, tuple[object, ...]]] = []
    bot, _ = await logged_in(Reporting)
    bot.add_listener(on_boom, "boom")
    bot.dispatch("boom")
    for _ in range(5):
        await asyncio.sleep(0)
    assert reported == [("boom", "boom", ())]


async def test_wait_for_returns_the_next_matching_event() -> None:
    client, _ = await logged_in()

    def is_two(value: object) -> bool:
        return value == 2

    single = asyncio.create_task(client.wait_for("ping", check=is_two))
    pair = asyncio.create_task(client.wait_for("on_pair"))
    nothing = asyncio.create_task(client.wait_for("empty"))
    await asyncio.sleep(0)
    client.dispatch("ping", 1)
    client.dispatch("ping", 2)
    client.dispatch("pair", "a", "b")
    client.dispatch("empty")
    assert await single == 2
    assert await pair == ("a", "b")
    assert await nothing is None
    with pytest.raises(TimeoutError):
        await client.wait_for("never", timeout=0.01)


async def test_a_failing_check_fails_the_wait() -> None:
    client, _ = await logged_in()

    def broken(value: object) -> bool:
        raise ValueError(value)

    waiting = asyncio.create_task(client.wait_for("ping", check=broken))
    await asyncio.sleep(0)
    client.dispatch("ping", 1)
    with pytest.raises(ValueError, match="1"):
        await waiting


async def test_ready_waits_for_the_guilds_of_every_shard() -> None:
    client, _ = await logged_in()
    events = Recorder(client, "connect", "shard_ready", "ready", "guild_available", "guild_join")
    await feed(client, "READY", {
        "v": 10,
        "user": user(BOT, "shoalbot"),
        "guilds": [{"id": str(GUILD), "unavailable": True}],
        "session_id": "s",
        "resume_gateway_url": "wss://r",
        "application": {"id": str(APPLICATION), "flags": 0},
    })  # fmt: skip
    assert events.names() == ["connect"]
    assert not client.is_ready()
    await feed(client, "GUILD_CREATE", guild_create())
    assert events.names() == ["connect", "guild_available", "shard_ready", "ready"]
    await client.wait_until_ready()
    assert events.args("shard_ready") == (0,)


async def test_a_guild_that_never_arrives_does_not_block_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "GUILD_READY_TIMEOUT", 0.01)
    client, _ = await logged_in()
    events = Recorder(client, "ready")
    ready = {
        "v": 10,
        "user": user(BOT, "shoalbot"),
        "guilds": [{"id": "999", "unavailable": True}],
        "session_id": "s",
        "resume_gateway_url": "wss://r",
        "application": {"id": str(APPLICATION), "flags": 0},
    }
    await feed(client, "READY", ready)
    await asyncio.sleep(0.05)
    assert events.names() == ["ready"]


async def test_resumed_is_reported() -> None:
    client, _ = await logged_in()
    events = Recorder(client, "resumed", "shard_resumed")
    await feed(client, "RESUMED", None, shard=3)
    assert events.seen == [("shard_resumed", (3,)), ("resumed", ())]


async def test_cache_lookups_like_discord_py() -> None:
    client, _ = await started()
    assert [guild.id for guild in client.guilds] == [GUILD]
    guild = client.get_guild(GUILD)
    assert guild is not None
    assert {found.id for found in client.users} >= {BOT, ALICE}
    assert client.get_user(ALICE) is not None
    assert isinstance(client.get_channel(GENERAL), TextChannel)
    assert client.get_channel(999) is None
    assert isinstance(client.get_partial_messageable(5, guild_id=GUILD), PartialMessageable)
    assert [emoji.id for emoji in client.emojis] == [EMOJI]
    assert client.get_emoji(EMOJI) is not None
    assert client.get_stage_instance(50) is not None
    assert len(list(client.get_all_channels())) == 6
    assert len(list(client.get_all_members())) == 4


async def test_fetching_through_rest() -> None:
    client, transport = await started()
    transport.queue(200, user(ALICE, "alice"))
    assert (await client.fetch_user(ALICE)).id == ALICE
    transport.queue(
        200, {k: v for k, v in guild_create().items() if k not in {"joined_at", "large", "member_count"}}
    )
    assert (await client.fetch_guild(GUILD)).name == "Shoal Test"
    transport.queue(200, channel(GENERAL, 0, "general"))
    assert isinstance(await client.fetch_channel(GENERAL), TextChannel)


async def test_interactions_go_to_handlers_until_one_takes_them() -> None:
    client, _ = await started()
    seen: list[str] = []

    async def declines(interaction: Interaction) -> bool:
        del interaction
        seen.append("declines")
        return False

    async def takes(interaction: Interaction) -> bool:
        del interaction
        seen.append("takes")
        return True

    async def never(interaction: Interaction) -> bool:
        del interaction
        seen.append("never")
        return True

    for handler in (declines, takes, never):
        client.add_interaction_handler(handler)
    events = Recorder(client, "interaction")
    await feed(client, "INTERACTION_CREATE", command("ping"))
    assert seen == ["declines", "takes"]
    assert events.names() == ["interaction"]


async def test_unknown_interaction_types_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    client, _ = await started()
    unknown = {"id": "1", "application_id": str(APPLICATION), "type": 99, "token": "t", "version": 1}
    with caplog.at_level(logging.WARNING, logger="shoal.client"):
        await feed(client, "INTERACTION_CREATE", unknown)
    assert "does not know" in caplog.text


async def test_only_persistent_views_can_be_added_without_a_message() -> None:
    client, _ = await logged_in()
    with pytest.raises(ValueError, match="persistent"):
        client.add_view(PersistentView(persistent=False))
    view = PersistentView()
    client.add_view(view)
    assert client.persistent_views == [view]
    client.add_view(PersistentView(persistent=False), message_id=5)
    assert client.persistent_views == [view]


class FakeShard:
    def __init__(self) -> None:
        self.presences: list[UpdatePresence] = []
        self.latency: float | None = 0.1

    async def update_presence(self, presence: UpdatePresence) -> None:
        self.presences.append(presence)


class FakeManager:
    made: ClassVar[list["FakeManager"]] = []

    def __init__(
        self,
        *,
        token: str,
        dispatch: DispatchHandler,
        shard_count: int,
        shard_ids: Sequence[int],
        presence: UpdatePresence,
        **options: object,
    ) -> None:
        del options
        self.token, self.dispatch, self.shard_count, self.shard_ids = token, dispatch, shard_count, shard_ids
        self.presence = presence
        self.shards = {shard_id: FakeShard() for shard_id in shard_ids}
        self.closed = False
        FakeManager.made.append(self)

    async def run(self) -> None:
        return

    async def close(self) -> None:
        self.closed = True


GATEWAY_BOT = {
    "url": "wss://gateway.discord.gg",
    "shards": 2,
    "session_start_limit": {"total": 1000, "remaining": 999, "reset_after": 0, "max_concurrency": 1},
}


async def test_connect_runs_every_recommended_shard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "ShardManager", FakeManager)
    client, transport = await logged_in()
    transport.queue(200, GATEWAY_BOT)
    await client.connect("token")
    manager = FakeManager.made[-1]
    assert (manager.shard_count, list(manager.shard_ids), manager.token) == (2, [0, 1], "token")
    assert manager.dispatch == client.feed
    assert client.latency == pytest.approx(0.1)
    await client.change_presence(activity=Game("chess"), status=StatusType.IDLE)
    presence = manager.shards[0].presences[-1]
    assert presence.status is StatusType.IDLE
    assert presence.activities[0].type is ActivityType.PLAYING
    await client.close()
    await client.close()
    assert manager.closed
    assert client.is_closed()
    assert transport.closed


async def test_a_cluster_runs_only_its_shards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "ShardManager", FakeManager)

    class Cluster(Client):
        def __init__(self, *, intents: Intents, rest: Callable[[Token], RestClient]) -> None:
            super().__init__(intents=intents, rest=rest, shard_count=4, shard_ids=[2, 3])

    clustered, transport = await logged_in(Cluster)
    transport.queue(200, GATEWAY_BOT)
    await clustered.connect("token")
    assert list(FakeManager.made[-1].shard_ids) == [2, 3]
    assert FakeManager.made[-1].shard_count == 4


def test_run_closes_the_client() -> None:
    started_with: list[str] = []

    class Quick(Client):
        @override
        async def start(self, token: str) -> None:
            started_with.append(token)

    client = Quick(intents=INTENTS, activity=Game("x"))
    client.run("token", log_level=None)
    assert started_with == ["token"]
    assert client.is_closed()
