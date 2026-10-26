import asyncio
import inspect
import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import ClassVar, override

import msgspec
import pytest

from shoal.cache.entry import Source
from shoal.cache.guild import CachedGuild
from shoal.cache.store import CacheStore
from shoal.client import client as client_module
from shoal.client.client import Client, ClientError, ClientOptions, Listener
from shoal.client.interaction import Interaction
from shoal.core.codec import encode_json
from shoal.core.dispatch import DispatchEvent, DispatchHandler
from shoal.core.metrics import InMemoryMetrics
from shoal.core.replies import REPLY_WRITTEN
from shoal.core.snowflake import Snowflake
from shoal.gateway.cluster import MemoryCommandRouter, MemoryShardDirectory
from shoal.gateway.session import MemorySessionStore
from shoal.gateway.shard import ShardOptions
from shoal.gateway.sharding import LocalIdentifyLimiter
from shoal.models.activity import Game
from shoal.models.channel import PartialMessageable, TextChannel
from shoal.models.state import GatewayRequiredError, MemberRequestRateLimitedError
from shoal.models.voice import SendVoiceState
from shoal.payloads import (
    ActivityType,
    ApplicationDeauthorized,
    DeferredMessageResponse,
    GatewayOpcode,
    Intents,
    MessageResponse,
    RequestGuildMembers,
    StatusType,
    UnknownInteraction,
    UpdatePresence,
    WebhookEventBody,
    WebhookEventPayload,
    WebhookEventType,
    parse_interaction,
)
from shoal.rest.client import RestClient, Token
from shoal.rest.errors import UnauthorizedError
from shoal.rest.files import File
from tests.support.calls import call_unchecked
from tests.support.client import INTENTS, Recorder, feed, logged_in, queue_login, receive_test_guild, started
from tests.support.endpoint import post, url_of
from tests.support.fakes import FakeTransport, settle
from tests.support.interactions import PersistentView, command, component, payload
from tests.support.models import (
    ALICE,
    APPLICATION,
    BOB,
    BOT,
    EMOJI,
    GENERAL,
    GUILD,
    channel,
    decoded,
    guild_create,
    member,
    message,
    user,
)
from tests.support.rest import make_client
from tests.support.signing import PUBLIC


async def test_login_learns_who_the_bot_is() -> None:
    client, transport = await logged_in()
    assert client.user is not None
    assert client.user.id == BOT
    assert client.application_id == APPLICATION
    assert [request.url.rsplit("/v10", 1)[1] for request in transport.requests] == [
        "/users/@me",
        "/applications/@me",
        f"/applications/{APPLICATION}/emojis",
    ]


async def test_a_failed_login_closes_its_rest_client_and_a_second_login_is_refused() -> None:
    transport = FakeTransport()
    made: list[RestClient] = []

    def rest(token: Token) -> RestClient:
        made.append(make_client(transport, token=token))
        return made[-1]

    client = Client(intents=INTENTS, rest=rest)
    transport.queue(401, {"message": "401: Unauthorized", "code": 0})
    with pytest.raises(UnauthorizedError):
        await client.login("wrong")
    assert transport.closed
    assert client.user is None
    logged, _ = await logged_in()
    with pytest.raises(ClientError, match="already logged in"):
        await logged.login("again")


async def test_the_bots_user_follows_user_update() -> None:
    client, _ = await started()
    me = client.user
    assert me is not None
    await feed(client, "USER_UPDATE", user(BOT, "renamed") | {"verified": True})
    assert client.user is me
    assert me.name == "renamed"
    assert me.verified


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


async def test_cache_lookups() -> None:
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
        self.member_requests: list[RequestGuildMembers] = []
        self.latency: float | None = 0.1

    async def update_presence(self, presence: UpdatePresence) -> None:
        self.presences.append(presence)

    async def request_guild_members(self, request: RequestGuildMembers) -> None:
        self.member_requests.append(request)


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
        self.options = options
        self.token, self.dispatch, self.shard_count, self.shard_ids = token, dispatch, shard_count, shard_ids
        self.presence = presence
        self.shards = {shard_id: FakeShard() for shard_id in shard_ids}
        self.closed = False
        self.resharded: tuple[int, Sequence[int] | None] | None = None
        self.voice_states: list[tuple[int, object]] = []
        FakeManager.made.append(self)

    async def run(self) -> None:
        return

    async def close(self) -> None:
        self.closed = True

    def shard_for_guild(self, guild_id: int) -> FakeShard | None:
        del guild_id
        return self.shards[0]

    async def send_to_guild(self, guild_id: int, opcode: GatewayOpcode, data: msgspec.Struct) -> None:
        assert opcode is GatewayOpcode.VOICE_STATE_UPDATE
        self.voice_states.append((guild_id, msgspec.json.decode(encode_json(data))))

    async def update_presence(self, presence: UpdatePresence) -> None:
        for shard in self.shards.values():
            await shard.update_presence(presence)

    async def reshard(self, shard_count: int, shard_ids: Sequence[int] | None) -> None:
        self.resharded = (shard_count, shard_ids)
        self.shard_count = shard_count
        self.shards = {shard_id: FakeShard() for shard_id in shard_ids or range(shard_count)}


GATEWAY_BOT = {
    "url": "wss://gateway.discord.gg",
    "shards": 2,
    "session_start_limit": {"total": 1000, "remaining": 999, "reset_after": 0, "max_concurrency": 1},
}


async def test_connect_passes_the_clients_gateway_options_to_every_shard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "ShardManager", FakeManager)
    transport = FakeTransport()
    metrics = InMemoryMetrics()
    store = MemorySessionStore()
    limiter = LocalIdentifyLimiter(16)
    client = Client(
        intents=INTENTS,
        rest=lambda token: make_client(transport, token=token),
        metrics=metrics,
        session_store=store,
        identify_limiter=limiter,
        large_threshold=100,
        compression=None,
    )
    queue_login(transport)
    await client.login("token")
    transport.queue(200, GATEWAY_BOT)
    await client.connect("token")
    options = FakeManager.made[-1].options
    assert options["metrics"] is metrics
    assert options["session_store"] is store
    assert options["identify_limiter"] is limiter
    assert (options["large_threshold"], options["compression"]) == (100, None)
    await client.close()


async def test_guilds_left_while_offline_are_forgotten_once_every_shard_is_ready() -> None:
    cache = CacheStore()
    left = Snowflake(GUILD + 1000)
    previous = decoded(guild_create() | {"id": str(left)}, CachedGuild)
    await cache.put(cache.guilds, left, previous, Source.GATEWAY, scope=left, shard=0)
    transport = FakeTransport()
    client = Client(intents=INTENTS, cache=cache, rest=lambda token: make_client(transport, token=token))
    queue_login(transport)
    await client.login("token")
    await receive_test_guild(client)
    assert client.get_guild(left) is None
    assert client.get_guild(GUILD) is not None


async def test_the_cache_snapshot_is_saved_after_the_shards_close_and_loaded_before_they_connect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(client_module, "ShardManager", FakeManager)
    snapshot = tmp_path / "cache.msgpack"

    async def run_once() -> Client:
        transport = FakeTransport()
        client = Client(
            intents=INTENTS, rest=lambda token: make_client(transport, token=token), cache_snapshot=snapshot
        )
        queue_login(transport)
        await client.login("token")
        transport.queue(200, GATEWAY_BOT)
        await client.connect("token")
        return client

    first = await run_once()
    await receive_test_guild(first)
    await first.close()
    assert snapshot.exists()
    second = await run_once()
    assert second.get_guild(GUILD) is not None
    await second.close()


async def test_connect_runs_every_recommended_shard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "ShardManager", FakeManager)
    client, transport = await logged_in()
    transport.queue(200, GATEWAY_BOT)
    await client.connect()
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


def shard_manager_of(client: Client) -> object:
    """Read through a function: checkers narrow a property across the awaits in between."""
    return client.shard_manager


async def test_a_reshard_goes_to_the_manager_once_session_starts_allow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "ShardManager", FakeManager)
    directory, router = MemoryShardDirectory(), MemoryCommandRouter()

    class Cluster(Client):
        def __init__(self, *, intents: Intents, rest: Callable[[Token], RestClient]) -> None:
            super().__init__(
                intents=intents,
                rest=rest,
                shard_directory=directory,
                command_router=router,
                cluster_name="cluster-1",
            )

    clustered, transport = await logged_in(Cluster)
    with pytest.raises(GatewayRequiredError):
        await clustered.reshard(4)
    assert shard_manager_of(clustered) is None
    transport.queue(200, GATEWAY_BOT)
    await clustered.connect("token")
    manager = FakeManager.made[-1]
    assert shard_manager_of(clustered) is manager
    assert (manager.options["directory"], manager.options["router"], manager.options["name"]) == (
        directory,
        router,
        "cluster-1",
    )
    transport.queue(200, GATEWAY_BOT)
    await clustered.reshard(4, [2, 3])
    assert manager.resharded == (4, [2, 3])
    assert clustered.cache.revision > 0  # the cache was told
    await clustered.close()


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


async def test_http_interactions_are_answered_in_the_http_reply() -> None:
    client, _ = await started()

    async def handler(interaction: Interaction) -> bool:
        await interaction.response.send_message("pong")
        return True

    client.add_interaction_handler(handler)
    reply = await client.handle_http(payload(command("ping")))
    assert isinstance(reply, MessageResponse)
    assert reply.data.content == "pong"


async def test_a_response_from_a_later_task_still_makes_the_reply() -> None:
    client, _ = await started()

    async def handler(interaction: Interaction) -> bool:
        async def later() -> None:
            await asyncio.sleep(0)
            await interaction.response.defer()

        _ = asyncio.get_running_loop().create_task(later())
        return True

    client.add_interaction_handler(handler)
    assert isinstance(await client.handle_http(payload(command("ping"))), DeferredMessageResponse)


async def test_files_and_late_responses_use_the_callback_endpoint(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    client, transport = await started()
    answered: list[Interaction] = []

    async def handler(interaction: Interaction) -> bool:
        answered.append(interaction)
        if interaction.id == 901:
            await interaction.response.send_message("file", file=File("a.txt", b"data"))
        return True

    client.add_interaction_handler(handler)
    transport.queue(204)
    assert await client.handle_http(payload(command("ping", interaction_id=901))) is None
    assert transport.requests[-1].url.endswith("/interactions/901/interaction-token/callback")

    monkeypatch.setattr(client_module, "INTERACTION_RESPONSE_DEADLINE", 0.01)
    with caplog.at_level(logging.WARNING, logger="shoal.client"):
        assert await client.handle_http(payload(command("ping", interaction_id=902))) is None
    assert "was not answered within" in caplog.text
    transport.queue(204)
    await answered[-1].response.send_message("too late")
    assert transport.requests[-1].url.endswith("/interactions/902/interaction-token/callback")


async def test_interactions_the_client_does_not_answer_get_no_reply() -> None:
    client, _ = await started()
    unknown = parse_interaction(encode_json({"id": "1", "application_id": "2", "type": 99, "token": "t"}))
    assert isinstance(unknown, UnknownInteraction)
    assert await client.handle_http(unknown) is None


async def test_an_endpoint_serves_the_clients_interactions() -> None:
    client, _ = await started()

    async def handler(interaction: Interaction) -> bool:
        await interaction.response.send_message("over http")
        return True

    client.add_interaction_handler(handler)
    async with client.endpoint(PUBLIC, port=0) as server:
        status, body = await post(url_of(server), command("ping"))
    assert status == 200
    assert msgspec.json.decode(body) == {"type": 4, "data": {"content": "over http"}}


async def test_code_after_an_http_answer_runs_once_discord_has_the_reply() -> None:
    client, transport = await started()
    view = PersistentView(persistent=False)
    reply_written: list[bool] = []

    async def handler(interaction: Interaction) -> bool:
        await interaction.response.send_message("vote", view=view)
        written = REPLY_WRITTEN.get()
        reply_written.append(written is not None and written.done())
        return True

    client.add_interaction_handler(handler)
    transport.queue(200, message(4321))
    async with client.endpoint(PUBLIC, port=0) as server:
        status, _ = await post(url_of(server), command("ping"))
        await settle()
    assert status == 200
    assert reply_written == [True]
    # The view is kept for the message the reply created, which only a fetch can tell.
    assert transport.requests[-1].url.endswith("/messages/@original")
    elsewhere = await client.process_interaction(payload(component("persistent:ok", message_id=1)))
    here = await client.process_interaction(payload(component("persistent:ok", message_id=4321)))
    assert view.received == [(here, "persistent:ok")]
    assert not elsewhere.response.is_done()


async def test_a_handler_answering_inline_does_not_hold_up_the_http_reply() -> None:
    client, _ = await started()

    async def handler(interaction: Interaction) -> bool:
        await interaction.response.send_message("inline")
        return True

    client.add_interaction_handler(handler)
    async with client.endpoint(PUBLIC, port=0) as server, asyncio.timeout(5):
        status, body = await post(url_of(server), command("ping"))
    assert status == 200
    assert msgspec.json.decode(body) == {"type": 4, "data": {"content": "inline"}}


async def test_a_subclass_handles_events_with_its_own_methods() -> None:
    seen: list[str] = []

    class Bot(Client):
        async def on_custom(self, value: str) -> None:
            seen.append(f"method {value}")

    bot, _ = await logged_in(Bot)
    bot.dispatch("custom", "a")
    await settle()

    @bot.event
    async def on_custom(value: str) -> None:
        seen.append(f"replaced {value}")

    bot.dispatch("custom", "b")
    bot.dispatch("error", "c")
    await settle()
    assert seen == ["method a", "replaced b"]


def test_client_options_name_every_keyword_of_the_client() -> None:
    parameters = inspect.signature(Client.__init__).parameters
    keywords = {
        name for name, parameter in parameters.items() if parameter.kind is inspect.Parameter.KEYWORD_ONLY
    }
    # Its own keys and, inherited, the shards' connection settings (`**options`).
    assert ClientOptions.__optional_keys__ == (keywords - {"intents"}) | ShardOptions.__optional_keys__


async def test_webhook_events_are_emitted_with_their_data() -> None:
    client, _ = await started()
    events = Recorder(client, "application_deauthorized", "something_new")
    event: dict[str, object] = {
        "type": "APPLICATION_DEAUTHORIZED",
        "timestamp": "2024-10-18T14:42:53.064834",
        "data": {"user": user(ALICE, "alice")},
    }
    body = {"version": 1, "application_id": str(APPLICATION), "type": 1, "event": event}
    payload = decoded(body, WebhookEventPayload)
    await client.handle_webhook_event(payload)
    newer = msgspec.structs.replace(
        payload,
        event=WebhookEventBody(type=WebhookEventType("SOMETHING_NEW"), timestamp=datetime(2024, 1, 1)),  # noqa: DTZ001
    )
    await client.handle_webhook_event(newer)
    ping: WebhookEventPayload = msgspec.structs.replace(payload, event=msgspec.UNSET)
    await client.handle_webhook_event(ping)
    await settle()
    [gone] = events.args("application_deauthorized")
    assert isinstance(gone, ApplicationDeauthorized)
    assert gone.user.id == ALICE
    assert events.args("something_new") == (newer,)


async def test_the_clients_endpoint_receives_webhook_events() -> None:
    client, _ = await started()
    events = Recorder(client, "application_deauthorized")
    async with client.endpoint(PUBLIC, port=0) as server:
        event = {
            "version": 1,
            "application_id": str(APPLICATION),
            "type": 1,
            "event": {
                "type": "APPLICATION_DEAUTHORIZED",
                "timestamp": "2024-10-18T14:42:53.064834",
                "data": {"user": user(ALICE, "alice")},
            },
        }
        status, _ = await post(url_of(server, "/events"), event)
        await settle()
    assert status == 204
    [gone] = events.args("application_deauthorized")
    assert isinstance(gone, ApplicationDeauthorized)


async def connected(monkeypatch: pytest.MonkeyPatch) -> tuple[Client, FakeShard]:
    """A logged-in client connected through a fake manager, with the test guild received."""
    monkeypatch.setattr(client_module, "ShardManager", FakeManager)
    client, transport = await logged_in()
    transport.queue(200, GATEWAY_BOT)
    await client.connect()
    await receive_test_guild(client)
    return client, FakeManager.made[-1].shards[0]


def chunk_of(request: RequestGuildMembers, index: int, count: int, *user_ids: int) -> dict[str, object]:
    assert isinstance(request.nonce, str)
    members = [member(user_id, f"user{user_id}") for user_id in user_ids]
    return {
        "guild_id": str(GUILD),
        "members": members,
        "chunk_index": index,
        "chunk_count": count,
        "nonce": request.nonce,
    }


async def test_chunking_a_guild_returns_every_member_and_shares_one_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, shard = await connected(monkeypatch)
    guild = client.get_guild(GUILD)
    assert guild is not None
    first = asyncio.create_task(guild.chunk())
    second = asyncio.create_task(guild.chunk())
    await settle()
    [request] = shard.member_requests
    assert (request.query, request.limit, request.presences) == ("", 0, False)
    await feed(client, "GUILD_MEMBERS_CHUNK", chunk_of(request, 0, 2, ALICE))
    await feed(client, "GUILD_MEMBERS_CHUNK", chunk_of(request, 1, 2, BOB))
    assert [found.id for found in await first] == [ALICE, BOB]
    assert [found.id for found in await second] == [ALICE, BOB]
    # Members cached before but not in the list left meanwhile.
    assert {found.id for found in guild.members} == {ALICE, BOB}


async def test_querying_members_by_name_or_id(monkeypatch: pytest.MonkeyPatch) -> None:
    client, shard = await connected(monkeypatch)
    guild = client.get_guild(GUILD)
    assert guild is not None
    by_name = asyncio.create_task(guild.query_members("al", limit=500))
    await settle()
    request = shard.member_requests[-1]
    assert (request.query, request.limit) == ("al", 100)
    await feed(client, "GUILD_MEMBERS_CHUNK", chunk_of(request, 0, 1, ALICE))
    assert [found.id for found in await by_name] == [ALICE]
    by_id = asyncio.create_task(guild.query_members(user_ids=[BOB]))
    await settle()
    request = shard.member_requests[-1]
    assert request.user_ids == [BOB]
    await feed(client, "GUILD_MEMBERS_CHUNK", chunk_of(request, 0, 1, BOB))
    assert [found.id for found in await by_id] == [BOB]
    with pytest.raises(ValueError, match="either"):
        await guild.query_members()
    with pytest.raises(ValueError, match="either"):
        await guild.query_members("a", user_ids=[1])
    with pytest.raises(ValueError, match="every member"):
        await guild.query_members("")
    with pytest.raises(ValueError, match="at least one"):
        await guild.query_members(user_ids=[])


async def test_a_rate_limited_member_request_fails_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    client, shard = await connected(monkeypatch)
    guild = client.get_guild(GUILD)
    assert guild is not None
    waiting = asyncio.create_task(guild.chunk())
    await settle()
    [request] = shard.member_requests
    limited = {"opcode": 8, "retry_after": 12.5, "meta": {"guild_id": str(GUILD), "nonce": request.nonce}}
    await feed(client, "RATE_LIMITED", limited)
    with pytest.raises(MemberRequestRateLimitedError) as refused:
        await waiting
    assert refused.value.retry_after == 12.5


async def test_member_requests_need_their_intents_a_gateway_and_an_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    offline, _ = await started()
    guild = offline.get_guild(GUILD)
    assert guild is not None
    with pytest.raises(GatewayRequiredError):
        await guild.query_members("a")
    client, _ = await connected(monkeypatch)
    online = client.get_guild(GUILD)
    assert online is not None
    client.intents = Intents.default()
    with pytest.raises(ClientError, match="Server Members"):
        await online.chunk()
    with pytest.raises(ClientError, match="Presence"):
        await online.query_members("a", presences=True)
    monkeypatch.setattr(client_module, "MEMBER_QUERY_TIMEOUT", 0.01)
    with pytest.raises(TimeoutError):
        await online.query_members("nobody")


class StubVoice:
    """Stands in for a guild's voice client: records what the client hands it."""

    made: ClassVar[list["StubVoice"]] = []
    failing: ClassVar[bool] = False

    def __init__(
        self,
        state: object,
        guild_id: int,
        *,
        send_state: SendVoiceState,
        forget: Callable[[object], None],
        metrics: object,
    ) -> None:
        del state
        self.guild_id = Snowflake(guild_id)
        self.send_state = send_state
        self.forget = forget
        self.metrics = metrics
        self.states: list[object] = []
        self.servers: list[object] = []
        self.joined: list[int] = []
        self.left = False
        StubVoice.made.append(self)

    async def connect(self, channel_id: int, *, self_mute: bool, self_deaf: bool) -> None:
        del self_mute, self_deaf
        if self.failing:
            msg = "no answer"
            raise TimeoutError(msg)
        self.joined.append(channel_id)

    def is_connected(self) -> bool:
        return bool(self.joined)

    def on_voice_state(self, state: object) -> None:
        self.states.append(state)

    def on_voice_server(self, server: object) -> None:
        self.servers.append(server)

    async def disconnect(self) -> None:
        self.left = True
        self.forget(self)


def voice_state_of(user: int, guild: int | None = GUILD, channel: int | None = 20) -> dict[str, object]:
    state: dict[str, object] = {
        "channel_id": None if channel is None else str(channel),
        "user_id": str(user),
        "session_id": "voice-session",
        "deaf": False,
        "mute": False,
        "self_deaf": False,
        "self_mute": False,
        "self_video": False,
        "suppress": False,
        "request_to_speak_timestamp": None,
    }
    if guild is not None:
        state["guild_id"] = str(guild)
    return state


async def test_voice_joins_through_the_guilds_shard_and_gets_its_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "VoiceClient", StubVoice)
    monkeypatch.setattr(client_module, "ShardManager", FakeManager)
    client, transport = await started()
    await client.connect_voice(GUILD, 20, self_mute=False, self_deaf=True)
    voice = StubVoice.made[-1]
    with pytest.raises(GatewayRequiredError, match="joining a voice channel"):
        await voice.send_state(GUILD, 20, self_mute=False, self_deaf=False)  # before connecting
    transport.queue(200, GATEWAY_BOT)
    await client.connect()
    manager = FakeManager.made[-1]
    assert client.voice_client(GUILD) is not None
    assert len(client.voice_clients) == 1
    await client.connect_voice(GUILD, 21, self_mute=False, self_deaf=False)
    assert StubVoice.made[-1] is voice  # one per guild
    assert voice.joined == [20, 21]
    # The voice state update goes out through the manager, to the guild's shard.
    await voice.send_state(GUILD, 20, self_mute=True, self_deaf=False)
    sent = {"guild_id": str(GUILD), "channel_id": "20", "self_mute": True, "self_deaf": False}
    assert manager.voice_states[-1] == (GUILD, sent)
    # Only the bot's own voice states reach the voice client, and only of its guild.
    await feed(client, "VOICE_STATE_UPDATE", voice_state_of(BOT))
    await feed(client, "VOICE_STATE_UPDATE", voice_state_of(ALICE))
    await feed(client, "VOICE_STATE_UPDATE", voice_state_of(BOT, guild=None))
    await feed(
        client, "VOICE_SERVER_UPDATE", {"token": "t", "guild_id": str(GUILD), "endpoint": "voice.test"}
    )
    await feed(client, "VOICE_SERVER_UPDATE", {"token": "t", "guild_id": "999", "endpoint": "voice.test"})
    assert (len(voice.states), len(voice.servers)) == (1, 1)
    await client.close()
    assert voice.left
    assert client.voice_clients == []


async def test_voice_clients_get_the_clients_metrics_and_all_leave_on_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "VoiceClient", StubVoice)
    metrics, transport = InMemoryMetrics(), FakeTransport()
    client = Client(intents=INTENTS, rest=lambda token: make_client(transport, token=token), metrics=metrics)
    queue_login(transport)
    await client.login("token")
    await client.connect_voice(GUILD, 20, self_mute=False, self_deaf=False)
    await client.connect_voice(GUILD + 1, 30, self_mute=False, self_deaf=False)
    first, second = StubVoice.made[-2:]
    assert first.metrics is metrics
    await client.close()
    assert first.left
    assert second.left
    assert client.voice_clients == []


async def test_a_failed_join_leaves_nothing_behind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "VoiceClient", StubVoice)
    monkeypatch.setattr(StubVoice, "failing", True)
    client, _ = await started()
    with pytest.raises(TimeoutError):
        await client.connect_voice(GUILD, 20, self_mute=False, self_deaf=False)
    assert client.voice_client(GUILD) is None
    await client.close()
