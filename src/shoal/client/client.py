"""The client: connect, receive events as models, answer interactions.

    client = shoal.Client(intents=shoal.Intents.default())

    @client.event
    async def on_ready() -> None:
        print(f"Logged in as {client.user}")

    @client.event
    async def on_message(message: shoal.Message) -> None:
        if message.content == "!ping":
            await message.reply("pong")

    client.run(token)

`run` connects every shard the gateway recommends, identifying as many at once as Discord allows,
and closes cleanly on Ctrl+C and SIGTERM. A worker that receives events from a gateway process
over `shoal.ipc` calls `login` and then `feed` for each event instead.

Discord: https://docs.discord.com/developers/events/gateway
"""

import asyncio
import contextlib
import inspect
import logging
import secrets
import signal
from collections.abc import Awaitable, Callable, Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final, Unpack, final

import msgspec
from msgspec import UNSET, UnsetType

from shoal.cache.store import CacheStore
from shoal.cache.updater import CacheUpdater
from shoal.client.defaults import (
    CHUNK_ATTEMPTS,
    GUILD_READY_TIMEOUT,
    MEMBER_LIST_MEMBERS_PER_SECOND,
    MEMBER_LIST_MIN_TIMEOUT,
    MEMBER_QUERY_TIMEOUT,
)
from shoal.client.events import EventTranslator
from shoal.client.interaction import Interaction, InteractionPayload, Responder, is_answerable
from shoal.client.views import DispatchableView, ViewStore
from shoal.core.clock import Clock, SystemClock, within
from shoal.core.codec import decode_json
from shoal.core.dispatch import DispatchEvent
from shoal.core.errors import ShoalError
from shoal.core.metrics import MEMBER_CHUNKS, Metrics, NoopMetrics
from shoal.core.replies import REPLY_WRITTEN
from shoal.core.snowflake import Snowflake
from shoal.core.tasks import spawn
from shoal.emojis.registry import AppEmojis
from shoal.gateway.cluster import CommandRouter, ShardDirectory
from shoal.gateway.manager import ShardManager
from shoal.gateway.session import SessionStore
from shoal.gateway.shard import ShardNotConnectedError, ShardOptions
from shoal.gateway.sharding import IdentifyLimiter, LocalIdentifyLimiter, wait_for_session_starts
from shoal.models.channel import (
    AnyGuildChannel,
    DMChannel,
    PartialMessageable,
    channel_from_payload,
    resolve_cached_channel,
)
from shoal.models.emoji import Emoji
from shoal.models.guild import Guild
from shoal.models.member import Member
from shoal.models.state import GatewayRequiredError, MemberRequestRateLimitedError, State
from shoal.models.user import ClientUser, User
from shoal.models.voice import VoiceClient
from shoal.payloads.gateway import GatewayOpcode, Intents
from shoal.payloads.gateway_events import (
    BotActivity,
    GuildMembersChunk,
    RateLimited,
    Ready,
    RequestGuildMembers,
    StatusType,
    UpdatePresence,
    UpdateVoiceState,
    VoiceServerUpdate,
)
from shoal.payloads.guild import GuildMember
from shoal.payloads.interactions import (
    INTERACTION_RESPONSE_DEADLINE,
    ComponentInteraction,
    ModalSubmitInteraction,
    UnknownInteraction,
    parse_interaction,
)
from shoal.payloads.interactions import Interaction as ReceivedInteraction
from shoal.payloads.interactions import InteractionResponse as ResponsePayload
from shoal.payloads.stage_instance import StageInstance
from shoal.payloads.user import User as UserPayload
from shoal.payloads.voice import VoiceState
from shoal.payloads.webhook_events import WEBHOOK_EVENT_PAYLOADS, WebhookEventPayload
from shoal.rest.client import RestClient, Token
from shoal.rest.files import File
from shoal.tasks.jobs import JobStore
from shoal.tasks.scheduler import Scheduler

if TYPE_CHECKING:
    from shoal.endpoint import Endpoint
    from shoal.models.thread import Thread

_log = logging.getLogger("shoal.client")

type Listener = Callable[..., Awaitable[None]]
"""An event handler: `async def on_message(message) -> None`."""
type InteractionHandler = Callable[[Interaction], Awaitable[bool]]
"""Takes an interaction (an application command tree does); returns whether it handled it."""

_CONNECTION_EVENTS: Final = frozenset({"READY", "RESUMED", "INTERACTION_CREATE"})

_VOICE_EVENTS: Final = frozenset({"VOICE_SERVER_UPDATE", "VOICE_STATE_UPDATE"})
"""Dispatches the guilds' voice clients wait for when joining."""


class ClientError(ShoalError):
    """The client was used in a way it cannot be, such as before `login`."""


@final
class _MemberRequest:
    """One Request Guild Members waiting for its chunks."""

    __slots__ = ("done", "guild_id", "members")

    def __init__(self, guild_id: int, done: asyncio.Future[list[GuildMember]]) -> None:
        self.guild_id: int = guild_id
        self.members: list[GuildMember] = []
        self.done: asyncio.Future[list[GuildMember]] = done


@final
class _GuildChunker:
    """Fetches the member list of each guild that arrives without it, one guild at a time per shard.

    One at a time: a shard's member requests share its gateway send limit with everything else it
    sends, and Discord allows one full member list per guild every 30 seconds. A shard's startup
    guilds hold its readiness back until they are chunked (`on_startup_done`).
    """

    __slots__ = (
        "_clock",
        "_fetch",
        "_metrics",
        "_on_startup_done",
        "_queued",
        "_queues",
        "_startup",
        "_workers",
    )

    def __init__(
        self,
        fetch: Callable[[Snowflake], Awaitable[None]],
        on_startup_done: Callable[[int], None],
        clock: Clock,
        metrics: Metrics,
    ) -> None:
        self._fetch: Callable[[Snowflake], Awaitable[None]] = fetch
        self._on_startup_done: Callable[[int], None] = on_startup_done
        self._clock: Clock = clock
        self._metrics: Metrics = metrics
        self._queues: dict[int, asyncio.Queue[Snowflake]] = {}
        self._workers: dict[int, asyncio.Task[None]] = {}
        self._queued: set[Snowflake] = set()
        """Guilds waiting or being chunked, so a guild is never asked for twice at once."""
        self._startup: dict[int, set[Snowflake]] = {}
        """Per shard, the guilds of its startup still being chunked."""

    def queue(self, shard_id: int, guild_id: Snowflake, *, startup: bool) -> None:
        if startup:
            self._startup.setdefault(shard_id, set()).add(guild_id)
        if guild_id in self._queued:
            return
        self._queued.add(guild_id)
        queue = self._queues.get(shard_id)
        if queue is None:
            queue = self._queues[shard_id] = asyncio.Queue()  # bounded: a guild is queued once at most
            self._workers[shard_id] = spawn(self._work(queue), name=f"shoal-chunk-{shard_id}")
        queue.put_nowait(guild_id)

    def chunking(self, shard_id: int) -> bool:
        """Whether startup guilds of the shard are still being chunked."""
        return bool(self._startup.get(shard_id))

    def new_session(self, shard_id: int) -> None:
        """The shard identified again: its guilds will arrive, and be counted, anew."""
        self._startup.pop(shard_id, None)

    def cancel(self) -> None:
        for worker in self._workers.values():
            worker.cancel()

    async def _work(self, queue: asyncio.Queue[Snowflake]) -> None:
        while True:
            guild_id = await queue.get()
            try:
                await self._chunk(guild_id)
            except Exception:  # noqa: BLE001 - one guild's failure must not stop its shard's chunking
                _log.exception("fetching the members of guild %d failed", guild_id)
                self._count("error")
            # Not on cancellation: the client is closing, and nothing becomes ready any more.
            self._queued.discard(guild_id)
            self._done(guild_id)

    async def _chunk(self, guild_id: Snowflake) -> None:
        for _ in range(CHUNK_ATTEMPTS):
            try:
                await self._fetch(guild_id)
            except MemberRequestRateLimitedError as limited:
                _log.debug(
                    "members of guild %d rate limited; asking again in %.1fs", guild_id, limited.retry_after
                )
                self._count("retried")
                await self._clock.sleep(limited.retry_after)
                continue
            except TimeoutError as error:
                _log.warning("could not fetch the members of guild %d: %r", guild_id, error)
                self._count("timeout")
            except (GatewayRequiredError, ShardNotConnectedError) as error:
                # The shard is reconnecting, or the guild moved: its next session chunks it again.
                _log.warning("could not fetch the members of guild %d: %r", guild_id, error)
                self._count("disconnected")
            else:
                self._count("fetched")
            return
        _log.warning(
            "could not fetch the members of guild %d: rate limited %d times", guild_id, CHUNK_ATTEMPTS
        )
        self._count("rate_limited")

    def _count(self, result: str) -> None:
        self._metrics.increment(MEMBER_CHUNKS, {"result": result})

    def _done(self, guild_id: Snowflake) -> None:
        # Every shard waiting on it: after a reshard, a guild queued by its old shard can be one of
        # its new shard's startup guilds.
        for shard_id, pending in list(self._startup.items()):
            if guild_id in pending:
                pending.discard(guild_id)
                if not pending:
                    del self._startup[shard_id]
                    self._on_startup_done(shard_id)


class _ArrivingGuild(msgspec.Struct):
    """What `GUILD_CREATE` says about a guild's members: how many it has, and which it carried."""

    id: Snowflake
    unavailable: bool = False
    member_count: int = 0
    members: list[msgspec.Raw] = []


@final
class _Waiter:
    __slots__ = ("check", "future")

    def __init__(self, check: Callable[..., bool] | None, future: asyncio.Future[tuple[object, ...]]) -> None:
        self.check: Callable[..., bool] | None = check
        self.future: asyncio.Future[tuple[object, ...]] = future


class ClientOptions(ShardOptions, total=False):
    """Every `Client` keyword but `intents`, for subclasses that pass them through (`commands.Bot`).

    Each key is the `Client` argument of the same name, with the same default.
    """

    cache: CacheStore | None
    chunk_guilds_at_startup: bool | None
    shard_count: int | None
    shard_ids: Sequence[int] | None
    activity: BotActivity | None
    status: StatusType
    rest: Callable[[Token], RestClient] | None
    app_emojis: AppEmojis | None
    metrics: Metrics | None
    session_store: SessionStore | None
    cache_snapshot: str | Path | None
    identify_limiter: IdentifyLimiter | None
    shard_directory: ShardDirectory | None
    command_router: CommandRouter | None
    cluster_name: str
    job_store: JobStore | None
    clock: Clock | None


class Client:
    """A bot: a gateway connection (or a stream of events), a cache, and models for every event.

    Args:
        intents: What events to receive. `Intents.default()` is every intent but the privileged
            ones (members, presences, message content), which must also be enabled in the
            Developer Portal.
        cache: The cache to keep; by default an in-memory `CacheStore`.
        chunk_guilds_at_startup: Fetch the member list of every guild that arrives without it, so the
            cache holds every member, as each guild streams in. `None` (the default) chunks when
            `intents` has the Server Members intent. Each shard requests one guild at a time and is
            ready (`on_shard_ready`, then `on_ready`) once its startup guilds are chunked; guilds
            joined later are chunked too. Large bots often turn it off and call `guild.chunk()`
            where they need every member.
        shard_count: Total shards; by default the number Discord recommends.
        shard_ids: The shards this process runs, for clusters; by default all of them.
        activity: The bot's activity on connect.
        status: The bot's status on connect.
        rest: Builds the REST client from the token, to set its other options:
            `rest=lambda token: RestClient(token, base_url=PROXY)` for a REST proxy.
        app_emojis: The registry of the application's emojis, to declare names and fallbacks
            with an `AppEmojis` subclass; by default an empty `AppEmojis`.
        metrics: Receives what the shards, the REST client (unless `rest` builds its own), the
            default cache and the HTTP endpoint measure.
        session_store: Where shard sessions are saved, so a restart resumes instead of identifying.
        cache_snapshot: A file for the cache: loaded before connecting and written after the shards
            close, so a restart answers from a warm cache (see the caching guide).
        identify_limiter: Shared by the shards; pass one every cluster shares (`shoal.redis`) so
            clusters together keep to `max_concurrency`. By default a local one.
        shard_directory: Where this cluster reports its shards and a reshard learns that every
            cluster's new shards are ready (`ShardManager`'s `directory`).
        command_router: Carries gateway commands for guilds on other clusters' shards (`ShardManager`'s
            `router`), such as joining a voice channel in a guild another cluster runs.
        cluster_name: How this cluster appears in the shard directory.
        job_store: Where `scheduler` keeps jobs; by default in memory. Pass a
            `shoal.redis.RedisJobStore` for jobs that survive restarts, shared by every cluster.
        clock: Time source for the client's timers, the shards, the default REST client and cache, and
            the models (`delete_after`, typing). Tests pass a fake one.
        options: How every shard connects (`ShardOptions`): `gateway_url`, `compression`,
            `large_threshold`, `capabilities`, `event_delay_warning`, `resume_window`.

    Subclass it and override `setup_hook` to run code (sync commands, add persistent views) after
    logging in and before connecting.

    Discord: https://docs.discord.com/developers/events/gateway
    """

    # A subclass without its own __slots__ still gets a __dict__, so `self.db = ...` keeps working.
    __slots__ = (
        "_app_emojis",
        "_cache",
        "_cache_snapshot",
        "_chunker",
        "_clock",
        "_closed",
        "_cluster_name",
        "_command_router",
        "_expected_shards",
        "_handlers",
        "_identify_limiter",
        "_interaction_handlers",
        "_listeners",
        "_make_rest",
        "_manager",
        "_member_lists",
        "_member_requests",
        "_metrics",
        "_pending_guilds",
        "_presence",
        "_ready",
        "_ready_shards",
        "_ready_timers",
        "_scheduler",
        "_session_store",
        "_shard_count",
        "_shard_directory",
        "_shard_ids",
        "_shard_options",
        "_state",
        "_token",
        "_translator",
        "_updater",
        "_user",
        "_views",
        "_voice_clients",
        "_waiters",
        "intents",
    )

    def __init__(
        self,
        *,
        intents: Intents,
        cache: CacheStore | None = None,
        chunk_guilds_at_startup: bool | None = None,
        shard_count: int | None = None,
        shard_ids: Sequence[int] | None = None,
        activity: BotActivity | None = None,
        status: StatusType = StatusType.ONLINE,
        rest: Callable[[Token], RestClient] | None = None,
        app_emojis: AppEmojis | None = None,
        metrics: Metrics | None = None,
        session_store: SessionStore | None = None,
        cache_snapshot: str | Path | None = None,
        identify_limiter: IdentifyLimiter | None = None,
        shard_directory: ShardDirectory | None = None,
        command_router: CommandRouter | None = None,
        cluster_name: str = "main",
        job_store: JobStore | None = None,
        clock: Clock | None = None,
        **options: Unpack[ShardOptions],
    ) -> None:
        """Create a client; see the class docstring for the arguments. Call `run` or `start`.

        Raises:
            ValueError: `chunk_guilds_at_startup` is true without the Server Members intent.
        """
        if chunk_guilds_at_startup and not intents.guild_members:
            msg = "chunk_guilds_at_startup needs the Server Members intent (guild_members)"
            raise ValueError(msg)
        self.intents: Intents = intents
        # Not `or`: a registry is empty, so falsy, until it loads at login.
        self._app_emojis: AppEmojis = app_emojis if app_emojis is not None else AppEmojis()
        self._metrics: Metrics = metrics or NoopMetrics()
        self._clock: Clock = clock or SystemClock()
        chunk = intents.guild_members if chunk_guilds_at_startup is None else chunk_guilds_at_startup
        self._chunker: _GuildChunker | None = (
            _GuildChunker(self._fetch_members, self._startup_chunked, self._clock, self._metrics)
            if chunk
            else None
        )
        self._session_store: SessionStore | None = session_store
        self._cache_snapshot: Path | None = Path(cache_snapshot) if cache_snapshot is not None else None
        self._identify_limiter: IdentifyLimiter | None = identify_limiter
        self._shard_directory: ShardDirectory | None = shard_directory
        self._command_router: CommandRouter | None = command_router
        self._cluster_name: str = cluster_name
        self._shard_options: ShardOptions = options
        self._cache: CacheStore = cache or CacheStore(metrics=self._metrics, clock=self._clock)
        self._updater: CacheUpdater = CacheUpdater(self._cache, intents=intents, metrics=self._metrics)
        self._views: ViewStore = ViewStore()
        self._make_rest: Callable[[Token], RestClient] = rest or (
            lambda token: RestClient(token, metrics=self._metrics, clock=self._clock)
        )
        self._shard_count: int | None = shard_count
        self._shard_ids: list[int] | None = list(shard_ids) if shard_ids is not None else None
        self._presence: UpdatePresence = UpdatePresence(
            since=None, activities=[activity] if activity is not None else [], status=status, afk=False
        )
        self._state: State | None = None
        self._member_requests: dict[str, _MemberRequest] = {}
        """Member requests waiting for chunks, by nonce."""
        self._member_lists: dict[int, _MemberRequest] = {}
        """Requests for every member, by guild: concurrent `guild.chunk()` calls share one."""
        self._token: str = ""
        """The bot token `login` used, for `connect`; never logged."""
        self._translator: EventTranslator | None = None
        self._manager: ShardManager | None = None
        self._user: ClientUser | None = None
        self._handlers: dict[str, Listener] = {}
        self._listeners: dict[str, list[Listener]] = {}
        self._waiters: dict[str, list[_Waiter]] = {}
        self._voice_clients: dict[int, VoiceClient] = {}
        self._interaction_handlers: list[InteractionHandler] = []
        self._ready: asyncio.Event | None = None
        self._expected_shards: set[int] | None = None
        self._ready_shards: set[int] = set()
        self._pending_guilds: dict[int, set[Snowflake]] = {}
        self._ready_timers: dict[int, asyncio.Task[None]] = {}
        self._closed: bool = False
        self._scheduler: Scheduler = Scheduler(job_store, clock=self._clock, metrics=self._metrics)

    @property
    def state(self) -> State:
        """The REST client, cache and identity every model uses.

        Raises:
            ClientError: Before `login`.
        """
        if self._state is None:
            msg = "the client is not logged in; call login() or start() first"
            raise ClientError(msg)
        return self._state

    @property
    def rest(self) -> RestClient:
        """The REST client: every endpoint as `rest.<resource>.<verb>`.

        Raises:
            ClientError: Before `login`.
        """
        return self.state.rest

    @property
    def cache(self) -> CacheStore:
        """The cache."""
        return self._cache

    @property
    def app_emojis(self) -> AppEmojis:
        """The application's own emojis, loaded at login: `client.app_emojis.approve`."""
        return self._app_emojis

    @property
    def scheduler(self) -> Scheduler:
        """Runs jobs at a time, after a delay or on a cron schedule (`shoal.tasks`).

        Register handlers with `scheduler.on(name)`; it starts running due jobs after `setup_hook`
        and stops on `close`.
        """
        return self._scheduler

    @property
    def view_store(self) -> ViewStore:
        """Where views and modals wait for their interactions."""
        return self._views

    async def login(self, token: str) -> None:
        """Check the token and learn who the bot is (and its application, for commands).

        Raises:
            UnauthorizedError: The token is wrong.
            ClientError: The client is already logged in.
        """
        if self._state is not None:
            msg = "the client is already logged in"
            raise ClientError(msg)
        rest = self._make_rest(Token.bot(token))
        state = State(
            rest=rest,
            cache=self._cache,
            views=self._views,
            clock=self._clock,
            member_requests=self,
            voice=self,
        )
        try:
            me = await rest.users.get_me()
            application = await rest.applications.get_me()
            state.identify(user_id=me.id, application_id=application.id)
            self._updater.identify(me.id)
            await self._app_emojis.load(state, application.id)
        except BaseException:
            # Nothing else holds the REST client yet, so `close` could not release it.
            await rest.close()
            raise
        self._state = state
        self._token = token
        self._user = ClientUser(state, me)
        self._translator = EventTranslator(state, self._updater, self.dispatch)
        await self.setup_hook()
        self._scheduler.start()  # after setup_hook, where handlers are registered

    async def setup_hook(self) -> None:
        """Runs once after `login` and before connecting; override it to sync commands or add views."""

    async def connect(self, token: str | None = None) -> None:
        """Connect the shards and process events until `close`, with the token `login` used.

        Raises:
            ClientError: Before `login`.
            GatewayFatalError: Discord refused the connection for good (bad token, intents not
                enabled in the Developer Portal).
        """
        rest = self.rest
        gateway = await rest.gateway.get_bot()
        shard_count = self._shard_count or gateway.shards
        shard_ids = self._shard_ids if self._shard_ids is not None else list(range(shard_count))
        await wait_for_session_starts(gateway.session_start_limit, len(shard_ids))
        if self._cache_snapshot is not None:
            # Before any shard connects: entries written meanwhile would lose to older ones.
            await self._cache.load_snapshot(self._cache_snapshot, shard_count=shard_count)
        self._expected_shards = set(shard_ids)
        self._manager = ShardManager(
            token=token if token is not None else self._token,
            intents=self.intents,
            dispatch=self.feed,
            shard_count=shard_count,
            shard_ids=shard_ids,
            identify_limiter=self._identify_limiter
            or LocalIdentifyLimiter(gateway.session_start_limit.max_concurrency),
            session_store=self._session_store,
            presence=self._presence,
            metrics=self._metrics,
            clock=self._clock,
            directory=self._shard_directory,
            router=self._command_router,
            name=self._cluster_name,
            **self._shard_options,
        )
        await self._manager.run()

    async def reshard(self, shard_count: int, shard_ids: Sequence[int] | None = None) -> None:
        """Move to `shard_count` shards without downtime (`ShardManager.reshard`).

        In clusters, call it in every cluster with the cluster's share of the new shards
        (`cluster_shard_ids`) and give them a shared `shard_directory`, so they hand over together.

        Raises:
            GatewayRequiredError: The client is not connected to the gateway.
            RuntimeError: Another reshard is in progress.
        """
        if self._manager is None:
            what = "resharding"
            raise GatewayRequiredError(what)
        gateway = await self.rest.gateway.get_bot()
        needed = len(shard_ids) if shard_ids is not None else shard_count
        await wait_for_session_starts(gateway.session_start_limit, needed)
        await self._manager.reshard(shard_count, shard_ids)
        self._cache.resharded()
        self._expected_shards = set(self._manager.shards)

    async def start(self, token: str) -> None:
        """`login`, then `connect`."""
        await self.login(token)
        await self.connect(token)

    async def close(self) -> None:
        """Disconnect every shard (resumably) and close the REST client. Safe to call twice."""
        if self._closed:
            return
        self._closed = True
        for timer in self._ready_timers.values():
            timer.cancel()
        if self._chunker is not None:
            self._chunker.cancel()
        await self._scheduler.close()  # before the REST client: running jobs may still use it
        # Together: each waits on its voice server, and a few unreachable ones must not add up.
        await asyncio.gather(*(voice.disconnect() for voice in list(self._voice_clients.values())))
        if self._manager is not None:
            await self._manager.close()
            if self._cache_snapshot is not None:
                # After the shards: the snapshot then ends at the event their saved sessions resume from.
                await self._cache.save_snapshot(self._cache_snapshot, shard_count=self._manager.shard_count)
        if self._state is not None:
            await self._state.rest.close()

    @property
    def voice_clients(self) -> list[VoiceClient]:
        """The bot's voice clients, one per guild where it is in a voice channel."""
        return list(self._voice_clients.values())

    def voice_client(self, guild_id: int, /) -> VoiceClient | None:
        """The guild's voice client, while the bot is in one of its voice channels."""
        return self._voice_clients.get(guild_id)

    async def connect_voice(
        self, guild_id: int, channel_id: int, /, *, self_mute: bool, self_deaf: bool
    ) -> VoiceClient:
        """Join (or move to) a voice channel; `VoiceChannel.connect` calls this.

        The voice state update goes out on the guild's shard; with a `command_router`, through the
        cluster running it. The answers arrive there, so voice is joined from that cluster.

        Raises:
            GatewayRequiredError: The client is not connected to the gateway.
            TimeoutError: Discord did not answer, or the voice handshake did not finish, in time.
            VoiceConnectionClosedError: The voice server refused the connection.

        Discord: https://docs.discord.com/developers/topics/voice-connections#connecting-to-voice
        """
        voice = self._voice_clients.get(guild_id)
        if voice is None:
            voice = VoiceClient(
                self.state,
                guild_id,
                send_state=self._send_voice_state,
                forget=self._forget_voice,
                metrics=self._metrics,
            )
            self._voice_clients[guild_id] = voice
        try:
            await voice.connect(channel_id, self_mute=self_mute, self_deaf=self_deaf)
        except BaseException:
            if not voice.is_connected():
                await voice.disconnect()
            raise
        return voice

    async def _send_voice_state(
        self, guild_id: int, channel_id: int | None, *, self_mute: bool, self_deaf: bool
    ) -> None:
        manager = self._manager
        if manager is None:
            what = "joining a voice channel"
            raise GatewayRequiredError(what)
        update = UpdateVoiceState(
            guild_id=Snowflake(guild_id),
            channel_id=None if channel_id is None else Snowflake(channel_id),
            self_mute=self_mute,
            self_deaf=self_deaf,
        )
        await manager.send_to_guild(guild_id, GatewayOpcode.VOICE_STATE_UPDATE, update)

    def _forget_voice(self, voice: VoiceClient) -> None:
        if self._voice_clients.get(int(voice.guild_id)) is voice:
            del self._voice_clients[int(voice.guild_id)]

    def _voice_event(self, event: DispatchEvent) -> None:
        """Hand the bot's own voice state and voice server updates to the guild's voice client."""
        if event.name == "VOICE_SERVER_UPDATE":
            server = event.decode(VoiceServerUpdate)
            voice = self._voice_clients.get(int(server.guild_id))
            if voice is not None:
                voice.on_voice_server(server)
            return
        update = event.decode(VoiceState)
        if not isinstance(update.guild_id, Snowflake) or update.user_id != self.state.user_id:
            return
        voice = self._voice_clients.get(int(update.guild_id))
        if voice is not None:
            voice.on_voice_state(update)

    def is_closed(self) -> bool:
        """Whether `close` was called."""
        return self._closed

    def run(self, token: str, *, log_level: int | None = logging.INFO) -> None:
        """Start the bot and block until it stops; closes cleanly on Ctrl+C and SIGTERM.

        Logging is set up at `log_level` unless it is `None` or logging is already configured.
        """
        if log_level is not None and not logging.getLogger().handlers:
            logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")

        async def runner() -> None:
            loop = asyncio.get_running_loop()
            stopping = asyncio.Event()
            for signum in (signal.SIGINT, signal.SIGTERM):
                with contextlib.suppress(NotImplementedError, RuntimeError):
                    # Windows has no loop signal handlers; Ctrl+C still raises KeyboardInterrupt there.
                    loop.add_signal_handler(signum, stopping.set)
            work = asyncio.create_task(self.start(token), name="shoal-client")
            stop = asyncio.create_task(stopping.wait(), name="shoal-client-stop")
            try:
                await asyncio.wait({work, stop}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                await self.close()
                stop.cancel()
                if not work.done():
                    work.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await work

        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(runner())

    def event[F: Listener](self, function: F, /) -> F:
        """Make `function` the handler for the event its name says (`on_message`), replacing any earlier one.

        It also replaces a subclass's own `on_message` method. Handlers added with `listen` or
        `add_listener` run as well.

        Raises:
            TypeError: `function` is not a coroutine function, or its name does not start with `on_`.
        """
        self._check_listener(function)
        self._handlers[function.__name__.removeprefix("on_")] = function
        return function

    def listen[F: Listener](self, name: str | None = None) -> Callable[[F], F]:
        """A decorator that adds a handler for an event, next to any others (`@client.listen()`)."""

        def decorator(function: F) -> F:
            self.add_listener(function, name)
            return function

        return decorator

    def add_listener(self, function: Listener, name: str | None = None) -> None:
        """Add a handler for `name` (default: the function's name without `on_`)."""
        self._check_listener(function, need_prefix=name is None)
        event = (name or function.__name__).removeprefix("on_")
        self._listeners.setdefault(event, []).append(function)

    def remove_listener(self, function: Listener, name: str | None = None) -> None:
        """Remove a handler added with `add_listener`, `listen` or `event`."""
        event = (name or function.__name__).removeprefix("on_")
        if self._handlers.get(event) is function:
            del self._handlers[event]
        with contextlib.suppress(ValueError):
            self._listeners.get(event, []).remove(function)

    @staticmethod
    def _check_listener(function: Listener, *, need_prefix: bool = True) -> None:
        if not inspect.iscoroutinefunction(function):
            msg = f"{function.__name__} must be a coroutine function (async def)"
            raise TypeError(msg)
        if need_prefix and not function.__name__.startswith("on_"):
            msg = f"{function.__name__} must be named after its event, such as on_message"
            raise TypeError(msg)

    def dispatch(self, event: str, /, *args: object) -> None:
        """Run every handler for `event` with `args`, each in its own task, and wake `wait_for`s."""
        for waiter in list(self._waiters.get(event, [])):
            if waiter.future.done():
                self._waiters[event].remove(waiter)
                continue
            try:
                matched = waiter.check is None or waiter.check(*args)
            except Exception as error:  # noqa: BLE001 - handed to the waiting caller
                waiter.future.set_exception(error)
                self._waiters[event].remove(waiter)
                continue
            if matched:
                waiter.future.set_result(args)
                self._waiters[event].remove(waiter)
        handler = self._handlers.get(event) or self._method_for(event)
        handlers = (
            [handler, *self._listeners.get(event, [])]
            if handler is not None
            else self._listeners.get(event, [])
        )
        for handler in handlers:
            _ = spawn(self._run_handler(event, handler, args), name=f"shoal-event-{event}")

    def _method_for(self, event: str) -> Listener | None:
        """A subclass's `on_<event>` method, which handles the event unless `event` replaced it.

        Methods `Client` itself defines (`on_error`) are hooks, not event handlers.
        """
        name = f"on_{event}"
        if hasattr(Client, name):
            return None
        method = getattr(self, name, None)
        return method if inspect.iscoroutinefunction(method) else None

    async def _run_handler(self, event: str, handler: Listener, args: tuple[object, ...]) -> None:
        try:
            await handler(*args)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - reported through on_error
            await self.on_error(event, error, *args)

    async def on_error(self, event: str, error: Exception, /, *args: object) -> None:
        """Called when a handler raises; logs the error. Override it to report errors elsewhere."""
        del args
        _log.error("handler for %s raised", event, exc_info=error)

    async def wait_for(
        self,
        event: str,
        /,
        *,
        check: Callable[..., bool] | None = None,
        timeout: float | None = None,  # noqa: ASYNC109 - a deadline for the wait, not for an operation
    ) -> object:
        """Wait for the next `event` that passes `check`; returns its argument (or a tuple of them).

        Raises:
            TimeoutError: `timeout` seconds passed first.
        """
        future: asyncio.Future[tuple[object, ...]] = asyncio.get_running_loop().create_future()
        name = event.removeprefix("on_")
        waiter = _Waiter(check, future)
        self._waiters.setdefault(name, []).append(waiter)
        try:
            args = await future if timeout is None else await within(self._clock, timeout, future)
        finally:
            # Timed out or cancelled: an event that never comes must not keep the waiter.
            waiting = self._waiters.get(name, [])
            if waiter in waiting:
                waiting.remove(waiter)
            if not waiting:
                self._waiters.pop(name, None)
        if not args:
            return None
        return args[0] if len(args) == 1 else args

    async def feed(self, event: DispatchEvent) -> None:
        """Process one gateway dispatch: update the cache and emit its events.

        The shards call it; a worker receiving events from `shoal.ipc` calls it for each one.

        Raises:
            ClientError: Before `login`.
        """
        translator = self._translator
        if translator is None:
            msg = "the client is not logged in; call login() before feeding events"
            raise ClientError(msg)
        self.dispatch("socket_event_type", event.name)
        if event.name == "USER_UPDATE" and self._user is not None:
            # Sent only for the bot's own user.
            self._user.refresh(event.decode(UserPayload))
        if event.name == "RATE_LIMITED" and self._member_requests:
            self._member_request_refused(event.decode(RateLimited))
        if event.name in _VOICE_EVENTS and self._voice_clients:
            self._voice_event(event)
        if event.name == "READY":
            await self._handle_ready(event)
        elif event.name == "RESUMED":
            await self._updater.apply(event)
            self.dispatch("shard_resumed", event.shard_id)
            self.dispatch("resumed")
            if event.shard_id not in self._ready_shards and event.shard_id not in self._pending_guilds:
                # A session saved before a restart: no READY comes, and its guilds are in the cache.
                # (A shard still receiving the guilds of its READY stays waiting for them.)
                self._shard_ready(event.shard_id)
        elif event.name == "INTERACTION_CREATE":
            await self._handle_interaction(event)
        else:
            await translator.translate(event)
            if event.name == "GUILD_CREATE":
                self._guild_arrived(event)
            elif event.name == "GUILD_MEMBERS_CHUNK" and self._member_requests:
                # After the cache took the chunk, so the members are there when the request ends.
                self._member_chunk(event.decode(GuildMembersChunk))

    def _ready_event(self) -> asyncio.Event:
        if self._ready is None:
            self._ready = asyncio.Event()
        return self._ready

    def is_ready(self) -> bool:
        """Whether every shard has received its guilds (or waited `GUILD_READY_TIMEOUT` for them)."""
        return self._ready is not None and self._ready.is_set()

    async def wait_until_ready(self) -> None:
        """Wait until `is_ready`."""
        await self._ready_event().wait()

    async def _handle_ready(self, event: DispatchEvent) -> None:
        ready = event.decode(Ready)
        await self._updater.apply(event)
        if self._state is not None:
            self._state.identify(user_id=ready.user.id, application_id=ready.application.id)
            self._user = ClientUser(self._state, ready.user)
        self._ready_shards.discard(event.shard_id)
        self._pending_guilds[event.shard_id] = {guild.id for guild in ready.guilds}
        if self._chunker is not None:
            self._chunker.new_session(event.shard_id)
        self.dispatch("connect")
        self._restart_ready_timer(event.shard_id)

    def _guild_arrived(self, event: DispatchEvent) -> None:
        arrived = event.decode(_ArrivingGuild)
        pending = self._pending_guilds.get(event.shard_id)
        if (
            self._chunker is not None
            and not arrived.unavailable
            and arrived.member_count > len(arrived.members)
        ):
            # A startup guild is one READY listed; a guild joined meanwhile holds nothing back.
            self._chunker.queue(
                event.shard_id, arrived.id, startup=pending is not None and arrived.id in pending
            )
        if not pending:
            return
        guild_id = arrived.id
        pending.discard(guild_id)
        if pending:
            self._restart_ready_timer(event.shard_id)
        else:
            self._shard_ready(event.shard_id)

    def _restart_ready_timer(self, shard_id: int) -> None:
        timer = self._ready_timers.pop(shard_id, None)
        if timer is not None:
            timer.cancel()
        if not self._pending_guilds.get(shard_id):
            self._shard_ready(shard_id)
            return

        async def expire() -> None:
            await self._clock.sleep(GUILD_READY_TIMEOUT)
            missing = len(self._pending_guilds.get(shard_id, ()))
            _log.info(
                "shard %d: %d guilds did not arrive in time; continuing without them", shard_id, missing
            )
            self._shard_ready(shard_id)

        self._ready_timers[shard_id] = spawn(expire(), name=f"shoal-ready-{shard_id}")

    def _shard_ready(self, shard_id: int) -> None:
        timer = self._ready_timers.pop(shard_id, None)
        if timer is not None and timer is not asyncio.current_task():
            timer.cancel()
        self._pending_guilds.pop(shard_id, None)
        if self._chunker is not None and self._chunker.chunking(shard_id):
            return  # every guild is in; the chunker calls again once their member lists are too
        if shard_id in self._ready_shards:
            return
        self._ready_shards.add(shard_id)
        self.dispatch("shard_ready", shard_id)
        expected = self._expected_shards
        if expected is not None and not expected <= self._ready_shards:
            return
        # Every shard has its guilds again: what is still stale is a guild the bot left meanwhile.
        _ = spawn(self._sweep_stale(), name="shoal-cache-sweep")
        if not self.is_ready():
            self._ready_event().set()
            self.dispatch("ready")

    async def _sweep_stale(self) -> None:
        await self._cache.sweep_stale()

    def _startup_chunked(self, shard_id: int) -> None:
        if shard_id not in self._pending_guilds:  # its guilds are all in, too
            self._shard_ready(shard_id)

    async def _fetch_members(self, guild_id: Snowflake) -> None:
        await self.request_members(guild_id, query="", limit=0, user_ids=None, presences=False)

    async def request_members(
        self,
        guild_id: int,
        /,
        *,
        query: str | None,
        limit: int,
        user_ids: Sequence[int] | None,
        presences: bool,
    ) -> list[GuildMember]:
        """Send a Request Guild Members on the guild's shard and gather its chunks.

        `guild.chunk()` and `guild.query_members()` call this.

        Raises:
            ClientError: The intent the request needs is missing.
            GatewayRequiredError: The guild's shard is not connected here.
            MemberRequestRateLimitedError: Discord refused the request for now.
            TimeoutError: The chunks did not all arrive in time.

        Discord: https://docs.discord.com/developers/events/gateway-events#request-guild-members
        """
        full = query == "" and limit == 0
        if full and not self.intents.guild_members:
            msg = "fetching every member needs the Server Members intent (guild_members)"
            raise ClientError(msg)
        if presences and not self.intents.guild_presences:
            msg = "members' presences need the Presence intent (guild_presences)"
            raise ClientError(msg)
        timeout = self._member_request_timeout(guild_id) if full else MEMBER_QUERY_TIMEOUT
        shared = self._member_lists.get(guild_id) if full else None
        if shared is not None:
            return await within(self._clock, timeout, asyncio.shield(shared.done))
        shard = self._manager.shard_for_guild(guild_id) if self._manager is not None else None
        if shard is None:
            what = "requesting members"
            raise GatewayRequiredError(what)
        nonce = secrets.token_hex(16)
        request = _MemberRequest(guild_id, asyncio.get_running_loop().create_future())
        self._member_requests[nonce] = request
        if full:
            self._member_lists[guild_id] = request
            self._updater.expect_member_list(nonce)
        try:
            await shard.request_guild_members(
                RequestGuildMembers(
                    guild_id=Snowflake(guild_id),
                    query=UNSET if query is None else query,
                    limit=limit,
                    presences=presences,
                    user_ids=UNSET if user_ids is None else [Snowflake(user) for user in user_ids],
                    nonce=nonce,
                )
            )
            return await within(self._clock, timeout, asyncio.shield(request.done))
        finally:
            self._member_requests.pop(nonce, None)
            if self._member_lists.get(guild_id) is request:
                del self._member_lists[guild_id]
            self._updater.forget_member_list(nonce)

    def _member_request_timeout(self, guild_id: int) -> float:
        cached = self.cache.peek(self.cache.guilds, Snowflake(guild_id))
        members = cached.member_count if cached is not None and isinstance(cached.member_count, int) else 0
        return max(MEMBER_LIST_MIN_TIMEOUT, members / MEMBER_LIST_MEMBERS_PER_SECOND)

    def _member_chunk(self, chunk: GuildMembersChunk) -> None:
        request = self._member_requests.get(chunk.nonce) if isinstance(chunk.nonce, str) else None
        if request is None or request.done.done():
            return
        request.members.extend(chunk.members)
        if chunk.chunk_index + 1 >= chunk.chunk_count:
            request.done.set_result(request.members)

    def _member_request_refused(self, limited: RateLimited) -> None:
        meta = limited.guild_members_metadata()
        if meta is None or not isinstance(meta.nonce, str):
            return
        request = self._member_requests.get(meta.nonce)
        if request is not None and not request.done.done():
            request.done.set_exception(MemberRequestRateLimitedError(request.guild_id, limited.retry_after))

    def add_interaction_handler(self, handler: InteractionHandler) -> None:
        """Give `handler` every command and autocomplete interaction first (a `CommandTree` does)."""
        self._interaction_handlers.append(handler)

    async def _handle_interaction(self, event: DispatchEvent) -> None:
        parsed = parse_interaction(event.data)
        if not is_answerable(parsed):
            _log.warning("received an interaction of a type this version of Shoal does not know")
            return
        await self.process_interaction(parsed)

    async def handle_http(self, data: ReceivedInteraction | UnknownInteraction) -> ResponsePayload | None:
        """Answer an interaction received over HTTP, for `Endpoint` (or `endpoint`, which builds one).

        The interaction goes through the same views, modals and command handlers as one from the
        gateway. Their first response becomes the HTTP reply; a response with files, or one given
        after Discord's 3-second deadline, goes through the callback endpoint instead.

        Raises:
            ClientError: The client has not logged in.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#responding-to-an-interaction
        """
        if not is_answerable(data):
            return None
        rest = self.state.rest
        answered: asyncio.Future[ResponsePayload | None] = asyncio.get_running_loop().create_future()
        written = REPLY_WRITTEN.get()

        async def respond(response: ResponsePayload, files: Sequence[File]) -> None:
            if files or answered.done():
                await rest.interactions.respond(data.id, data.token, response, files=files)
                if not answered.done():
                    answered.set_result(None)
                return
            answered.set_result(response)
            if written is not None:
                # Whatever the caller does next (a follow-up, an edit) needs the reply to exist.
                await asyncio.shield(written)

        # In its own task: a handler that answers inline waits for the reply, which is only written
        # once this returns.
        async def route() -> None:
            await self.process_interaction(data, responder=respond)

        _ = spawn(route(), name=f"shoal-http-interaction-{data.id}")
        try:
            return await within(self._clock, INTERACTION_RESPONSE_DEADLINE, answered)
        except TimeoutError:
            if answered.done() and not answered.cancelled():
                # Answered just as the deadline passed, before this task resumed: still the reply.
                return answered.result()
            # The timeout cancelled `answered`, so a later response goes through the callback endpoint.
            _log.warning(
                "interaction %s was not answered within %.0fs; defer when the work takes longer",
                data.id,
                INTERACTION_RESPONSE_DEADLINE,
            )
            return None

    def endpoint(
        self,
        public_key: str,
        *,
        host: str | None = None,
        port: int | None = None,
        path: str | None = None,
        events_path: str | None = None,
    ) -> "Endpoint":
        """An `Endpoint` answering interactions over HTTP through this client.

        `async with client.endpoint(public_key):` serves until the block ends. It also receives the
        app's webhook events on `events_path` (set it as the Webhook Events URL), emitted as events
        (`handle_webhook_event`).

        For bots without a gateway connection: log in, then serve. Needs `shoal[interactions]`.

        Raises:
            MissingDependencyError: `shoal[interactions]` is not installed.
            ValueError: `public_key` is not a valid Ed25519 public key.
        """
        from shoal.endpoint import Endpoint, defaults

        return Endpoint(
            public_key,
            self.handle_http,
            host=host if host is not None else defaults.HOST,
            port=port if port is not None else defaults.PORT,
            path=path if path is not None else defaults.PATH,
            events=self.handle_webhook_event,
            events_path=events_path if events_path is not None else defaults.EVENTS_PATH,
            metrics=self._metrics,
            clock=self._clock,
        )

    async def handle_webhook_event(self, payload: WebhookEventPayload) -> None:
        """Emit a webhook event as `on_<event type in lower case>` with its data, for `Endpoint`.

        `on_application_authorized(ApplicationAuthorized)`, `on_entitlement_create(Entitlement)` (the
        same event the gateway emits), `on_lobby_message_create(WebhookLobbyMessage)`, ... An event
        type Shoal does not know yet is emitted with the whole `WebhookEventPayload`.

        Raises:
            PayloadDecodeError: The data does not match its documented type.

        Discord: https://docs.discord.com/developers/events/webhook-events#event-types
        """
        event = payload.event
        if isinstance(event, UnsetType):
            return
        name = str(event.type).lower()
        kind = WEBHOOK_EVENT_PAYLOADS.get(event.type)
        if kind is None or isinstance(event.data, UnsetType):
            self.dispatch(name, payload)
            return
        self.dispatch(name, decode_json(event.data, kind))

    async def process_interaction(
        self, data: InteractionPayload, *, responder: Responder | None = None
    ) -> Interaction:
        """Route one interaction to views, modals and command handlers, and emit `on_interaction`.

        The gateway path calls this; an HTTP interactions server passes a `responder` that answers
        in the HTTP reply. Returns the interaction, for the caller to check `response.is_done()`.
        """
        interaction = Interaction(self, self.state, data, responder=responder)
        self.dispatch("interaction", interaction)
        if isinstance(data, ComponentInteraction):
            message_id = None if isinstance(data.message, UnsetType) else data.message.id
            await self._views.dispatch_component(interaction, data.data.custom_id, message_id)
        elif isinstance(data, ModalSubmitInteraction):
            await self._views.dispatch_modal(interaction, data.data.custom_id, interaction.user.id)
        else:
            for handler in self._interaction_handlers:
                if await handler(interaction):
                    break
        return interaction

    def add_view(self, view: DispatchableView, *, message_id: int | None = None) -> None:
        """Route a view's interactions to it, on one message or (persistent views) on any.

        Raises:
            ValueError: Without `message_id`, the view is not persistent (it has a timeout, or an
                item without a custom ID of its own).
        """
        if message_id is None and not view.is_persistent():
            msg = "a view added without a message must be persistent: timeout=None and fixed custom IDs"
            raise ValueError(msg)
        self._views.store(view, message_id=message_id)

    @property
    def persistent_views(self) -> list[DispatchableView]:
        """The views added for any message."""
        return self._views.persistent_views

    @property
    def user(self) -> ClientUser | None:
        """The bot's user, once logged in."""
        return self._user

    @property
    def application_id(self) -> Snowflake | None:
        """The bot's application ID, once logged in."""
        return self._state.application_id if self._state is not None else None

    @property
    def guilds(self) -> list[Guild]:
        """Every cached guild."""
        state = self.state
        return [Guild(state, entry.value) for _, entry in state.cache.guilds.peek_items()]

    @property
    def users(self) -> list[User]:
        """Every cached user."""
        state = self.state
        return [User(state, entry.value) for _, entry in state.cache.users.peek_items()]

    @property
    def emojis(self) -> list[Emoji]:
        """Every cached custom emoji, across guilds."""
        state = self.state
        return [
            Emoji(state, entry.value, entry.scope)
            for _, entry in state.cache.emojis.peek_items()
            if entry.scope is not None
        ]

    def get_guild(self, guild_id: int, /) -> Guild | None:
        """The cached guild with this ID."""
        return Guild.from_cache(self.state, guild_id)

    def get_user(self, user_id: int, /) -> User | None:
        """The cached user with this ID."""
        return User.from_cache(self.state, user_id)

    def get_channel(self, channel_id: int, /) -> "AnyGuildChannel | Thread | DMChannel | None":
        """The cached channel, thread or DM channel with this ID."""
        return resolve_cached_channel(self.state, channel_id)

    def get_partial_messageable(
        self, channel_id: int, /, *, guild_id: int | None = None
    ) -> PartialMessageable:
        """A channel known only by ID, to send messages without fetching it."""
        return PartialMessageable(self.state, channel_id, guild_id)

    def get_emoji(self, emoji_id: int, /) -> Emoji | None:
        """The cached custom emoji with this ID."""
        return Emoji.from_cache(self.state, emoji_id)

    def get_stage_instance(self, stage_instance_id: int, /) -> StageInstance | None:
        """The cached live stage with this ID."""
        return self.state.cache.peek(self.state.cache.stage_instances, Snowflake(stage_instance_id))

    def get_all_channels(self) -> Iterable[AnyGuildChannel]:
        """Every cached guild channel, guild by guild."""
        for guild in self.guilds:
            yield from guild.channels

    def get_all_members(self) -> Iterable[Member]:
        """Every cached member, guild by guild."""
        for guild in self.guilds:
            yield from guild.members

    async def fetch_user(self, user_id: int, /) -> User:
        """Get a user from Discord.

        Discord: https://docs.discord.com/developers/resources/user#get-user
        """
        return User(self.state, await self.rest.users.get(user_id))

    async def fetch_guild(self, guild_id: int, /, *, with_counts: bool = True) -> Guild:
        """Get a guild from Discord.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild
        """
        return Guild(self.state, await self.rest.guilds.get(guild_id, with_counts=with_counts))

    async def fetch_channel(self, channel_id: int, /) -> "AnyGuildChannel | Thread | DMChannel":
        """Get a channel or thread from Discord.

        Discord: https://docs.discord.com/developers/resources/channel#get-channel
        """
        return channel_from_payload(self.state, await self.rest.channels.get(channel_id))

    @property
    def shard_manager(self) -> ShardManager | None:
        """The shards this process runs, once connected; `None` before.

        Send a gateway command for any guild through it (`send_to_guild`): with a `command_router`
        it reaches guilds on the bot's other clusters too.
        """
        return self._manager

    @property
    def latency(self) -> float | None:
        """The average heartbeat round trip of the shards, in seconds, once measured."""
        if self._manager is None:
            return None
        measured = [shard.latency for shard in self._manager.shards.values() if shard.latency is not None]
        return sum(measured) / len(measured) if measured else None

    async def change_presence(
        self, *, activity: BotActivity | None = None, status: StatusType = StatusType.ONLINE
    ) -> None:
        """Change the bot's activity and status on every shard.

        Discord: https://docs.discord.com/developers/events/gateway-events#update-presence
        """
        self._presence = UpdatePresence(
            since=None, activities=[activity] if activity is not None else [], status=status, afk=False
        )
        if self._manager is not None:
            await self._manager.update_presence(self._presence)
