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
import signal
from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import TYPE_CHECKING, Final, final

from msgspec import UnsetType

from shoal.cache.store import CacheStore
from shoal.cache.updater import CacheUpdater
from shoal.client.defaults import GUILD_READY_TIMEOUT
from shoal.client.events import EventTranslator
from shoal.client.interaction import Interaction, InteractionPayload, Responder
from shoal.client.views import DispatchableView, ViewStore
from shoal.core.dispatch import DispatchEvent
from shoal.core.errors import ShoalError
from shoal.core.snowflake import Snowflake
from shoal.core.tasks import spawn
from shoal.gateway.manager import ShardManager
from shoal.gateway.sharding import LocalIdentifyLimiter
from shoal.models.channel import (
    AnyGuildChannel,
    MessageableChannel,
    PartialMessageable,
    channel_from_payload,
    resolve_guild_channel,
)
from shoal.models.emoji import Emoji
from shoal.models.guild import Guild
from shoal.models.member import Member
from shoal.models.state import State
from shoal.models.user import ClientUser, User
from shoal.payloads.gateway import Intents
from shoal.payloads.gateway_events import BotActivity, Ready, StatusType, UpdatePresence
from shoal.payloads.guild import UnavailableGuild
from shoal.payloads.interactions import (
    ApplicationCommandInteraction,
    AutocompleteInteraction,
    ComponentInteraction,
    ModalSubmitInteraction,
    UnknownInteraction,
    parse_interaction,
)
from shoal.payloads.stage_instance import StageInstance
from shoal.rest.client import RestClient, Token

if TYPE_CHECKING:
    from shoal.models.thread import Thread

_log = logging.getLogger("shoal.client")

type Listener = Callable[..., Awaitable[None]]
"""An event handler: `async def on_message(message) -> None`."""
type InteractionHandler = Callable[[Interaction], Awaitable[bool]]
"""Takes an interaction (an application command tree does); returns whether it handled it."""

_CONNECTION_EVENTS: Final = frozenset({"READY", "RESUMED", "INTERACTION_CREATE"})


class ClientError(ShoalError):
    """The client was used in a way it cannot be, such as before `login`."""


@final
class _Waiter:
    __slots__ = ("check", "future")

    def __init__(self, check: Callable[..., bool] | None, future: asyncio.Future[tuple[object, ...]]) -> None:
        self.check: Callable[..., bool] | None = check
        self.future: asyncio.Future[tuple[object, ...]] = future


class Client:
    """A bot: a gateway connection (or a stream of events), a cache, and models for every event.

    Args:
        intents: What events to receive. `Intents.default()` is every intent but the privileged
            ones (members, presences, message content), which must also be enabled in the
            Developer Portal.
        cache: The cache to keep; by default an in-memory `CacheStore`.
        shard_count: Total shards; by default the number Discord recommends.
        shard_ids: The shards this process runs, for clusters; by default all of them.
        activity: The bot's activity on connect.
        status: The bot's status on connect.
        rest: Options for the REST client other than the token, such as `base_url` for a REST proxy.

    Subclass it and override `setup_hook` to run code (sync commands, add persistent views) after
    logging in and before connecting.

    Discord: https://docs.discord.com/developers/events/gateway
    """

    # A subclass without its own __slots__ still gets a __dict__, so `self.db = ...` keeps working.
    __slots__ = (
        "_cache",
        "_closed",
        "_expected_shards",
        "_handlers",
        "_interaction_handlers",
        "_listeners",
        "_make_rest",
        "_manager",
        "_pending_guilds",
        "_presence",
        "_ready",
        "_ready_shards",
        "_ready_timers",
        "_shard_count",
        "_shard_ids",
        "_state",
        "_translator",
        "_updater",
        "_user",
        "_views",
        "_waiters",
        "intents",
    )

    def __init__(
        self,
        *,
        intents: Intents,
        cache: CacheStore | None = None,
        shard_count: int | None = None,
        shard_ids: Sequence[int] | None = None,
        activity: BotActivity | None = None,
        status: StatusType = StatusType.ONLINE,
        rest: Callable[[Token], RestClient] | None = None,
    ) -> None:
        """Create a client; see the class docstring for the arguments. Call `run` or `start`."""
        self.intents: Intents = intents
        self._cache: CacheStore = cache or CacheStore()
        self._updater: CacheUpdater = CacheUpdater(self._cache, intents=intents)
        self._views: ViewStore = ViewStore()
        self._make_rest: Callable[[Token], RestClient] = rest or RestClient
        self._shard_count: int | None = shard_count
        self._shard_ids: list[int] | None = list(shard_ids) if shard_ids is not None else None
        self._presence: UpdatePresence = UpdatePresence(
            since=None, activities=[activity] if activity is not None else [], status=status, afk=False
        )
        self._state: State | None = None
        self._translator: EventTranslator | None = None
        self._manager: ShardManager | None = None
        self._user: ClientUser | None = None
        self._handlers: dict[str, Listener] = {}
        self._listeners: dict[str, list[Listener]] = {}
        self._waiters: dict[str, list[_Waiter]] = {}
        self._interaction_handlers: list[InteractionHandler] = []
        self._ready: asyncio.Event | None = None
        self._expected_shards: set[int] | None = None
        self._ready_shards: set[int] = set()
        self._pending_guilds: dict[int, set[Snowflake]] = {}
        self._ready_timers: dict[int, asyncio.Task[None]] = {}
        self._closed: bool = False

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
    def view_store(self) -> ViewStore:
        """Where views and modals wait for their interactions."""
        return self._views

    async def login(self, token: str) -> None:
        """Check the token and learn who the bot is (and its application, for commands).

        Raises:
            UnauthorizedError: The token is wrong.
        """
        rest = self._make_rest(Token.bot(token))
        state = State(rest=rest, cache=self._cache, views=self._views)
        me = await rest.users.get_me()
        application = await rest.applications.get_me()
        state.identify(user_id=me.id, application_id=application.id)
        self._state = state
        self._user = ClientUser(state, me)
        self._translator = EventTranslator(state, self._updater, self.dispatch)
        await self.setup_hook()

    async def setup_hook(self) -> None:
        """Runs once after `login` and before connecting; override it to sync commands or add views."""

    async def connect(self, token: str) -> None:
        """Connect the shards and process events until `close`.

        Raises:
            ClientError: Before `login`.
            GatewayFatalError: Discord refused the connection for good (bad token, intents not
                enabled in the Developer Portal).
        """
        rest = self.rest
        gateway = await rest.gateway.get_bot()
        shard_count = self._shard_count or gateway.shards
        shard_ids = self._shard_ids if self._shard_ids is not None else list(range(shard_count))
        self._expected_shards = set(shard_ids)
        self._manager = ShardManager(
            token=token,
            intents=self.intents,
            dispatch=self.feed,
            shard_count=shard_count,
            shard_ids=shard_ids,
            identify_limiter=LocalIdentifyLimiter(gateway.session_start_limit.max_concurrency),
            presence=self._presence,
        )
        await self._manager.run()

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
        if self._manager is not None:
            await self._manager.close()
        if self._state is not None:
            await self._state.rest.close()

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

        Handlers added with `listen` or `add_listener` run as well.

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
        handler = self._handlers.get(event)
        handlers = (
            [handler, *self._listeners.get(event, [])]
            if handler is not None
            else self._listeners.get(event, [])
        )
        for handler in handlers:
            _ = spawn(self._run_handler(event, handler, args), name=f"shoal-event-{event}")

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
        self._waiters.setdefault(event.removeprefix("on_"), []).append(_Waiter(check, future))
        args = await asyncio.wait_for(future, timeout)
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
        if event.name == "READY":
            await self._handle_ready(event)
        elif event.name == "RESUMED":
            await self._updater.apply(event)
            self.dispatch("shard_resumed", event.shard_id)
            self.dispatch("resumed")
        elif event.name == "INTERACTION_CREATE":
            await self._handle_interaction(event)
        else:
            await translator.translate(event)
            if event.name == "GUILD_CREATE":
                self._guild_arrived(event)

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
        self.dispatch("connect")
        self._restart_ready_timer(event.shard_id)

    def _guild_arrived(self, event: DispatchEvent) -> None:
        pending = self._pending_guilds.get(event.shard_id)
        if not pending:
            return
        guild_id = event.decode(UnavailableGuild).id
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
            await asyncio.sleep(GUILD_READY_TIMEOUT)
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
        if shard_id in self._ready_shards:
            return
        self._ready_shards.add(shard_id)
        self.dispatch("shard_ready", shard_id)
        expected = self._expected_shards
        if (expected is None or expected <= self._ready_shards) and not self.is_ready():
            self._ready_event().set()
            self.dispatch("ready")

    def add_interaction_handler(self, handler: InteractionHandler) -> None:
        """Give `handler` every command and autocomplete interaction first (a `CommandTree` does)."""
        self._interaction_handlers.append(handler)

    async def _handle_interaction(self, event: DispatchEvent) -> None:
        parsed = parse_interaction(event.data)
        if isinstance(parsed, UnknownInteraction) or not isinstance(
            parsed,
            ApplicationCommandInteraction
            | ComponentInteraction
            | AutocompleteInteraction
            | ModalSubmitInteraction,
        ):
            _log.warning("received an interaction of a type this version of Shoal does not know")
            return
        await self.process_interaction(parsed)

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

    def get_channel(self, channel_id: int, /) -> "AnyGuildChannel | Thread | MessageableChannel | None":
        """The cached channel or thread with this ID."""
        return resolve_guild_channel(self.state, channel_id)

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

    async def fetch_channel(self, channel_id: int, /) -> "AnyGuildChannel | Thread | MessageableChannel":
        """Get a channel or thread from Discord.

        Discord: https://docs.discord.com/developers/resources/channel#get-channel
        """
        return channel_from_payload(self.state, await self.rest.channels.get(channel_id))

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
            await asyncio.gather(
                *(shard.update_presence(self._presence) for shard in self._manager.shards.values())
            )
