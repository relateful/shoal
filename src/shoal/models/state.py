"""What every model holds: the REST client, the cache, and who the bot is.

`shoal.Client` creates one `State` and hands it to every model it builds, so `message.reply(...)`
sends through the client's REST client and `guild.get_member(...)` reads the client's cache. A
dashboard or worker without a `Client` can build one itself:

    state = State(rest=RestClient(token), cache=CacheStore())
    guild = Guild(state, await state.rest.guilds.get(guild_id))
"""

import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, final, override

from shoal.cache.store import CacheStore
from shoal.core.clock import Clock, SystemClock
from shoal.core.errors import ShoalError
from shoal.core.snowflake import Snowflake
from shoal.core.tasks import spawn
from shoal.payloads.components import MessageComponent
from shoal.payloads.guild import GuildMember
from shoal.rest.client import RestClient
from shoal.rest.errors import NotFoundError

if TYPE_CHECKING:
    from shoal.models.voice import VoiceClient, VoiceGateway

_log = logging.getLogger("shoal.models")


class ComponentView(Protocol):
    """Something that renders a message's components and wants their interactions: a `ui.View`."""

    __slots__ = ()

    def to_components(self) -> list[MessageComponent]:
        """The components to send."""
        ...

    def is_dispatchable(self) -> bool:
        """Whether interactions with these components should be routed back to it."""
        ...


class ViewRegistry(Protocol):
    """Where views are kept so component interactions reach them: the client's view store."""

    __slots__ = ()

    def store(self, view: ComponentView, *, message_id: int | None) -> None:
        """Route interactions with `view`'s components (on `message_id`, when known) to it."""
        ...


class MemberRequests(Protocol):
    """Asks the gateway for a guild's members: a `Client`, through its shards."""

    __slots__ = ()

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
        """Request members (every member for `query=""` with `limit=0`); the members that came back.

        Raises:
            GatewayRequiredError: There is no gateway connection for the guild.
        """
        ...


class GatewayRequiredError(ShoalError):
    """This needs a gateway connection: a `Client` that connected, running the guild's shard."""

    def __init__(self, what: str) -> None:
        """`what` needs the gateway."""
        super().__init__(f"{what} needs a gateway connection to the guild's shard")


class MemberRequestRateLimitedError(ShoalError):
    """Discord refused a member request for now; try again after `retry_after` seconds.

    Discord: https://docs.discord.com/developers/events/gateway-events#rate-limited
    """

    def __init__(self, guild_id: int, retry_after: float) -> None:
        """Requests for guild `guild_id`'s members are limited for `retry_after` seconds."""
        super().__init__(f"member requests for guild {guild_id} are rate limited for {retry_after:.1f}s")
        self.guild_id: int = guild_id
        self.retry_after: float = retry_after


@final
class _NoGateway(MemberRequests):
    """Used without a connected client: member requests need a gateway."""

    __slots__ = ()

    @override
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
        del guild_id, query, limit, user_ids, presences
        what = "requesting members"
        raise GatewayRequiredError(what)


@final
class _NoVoice:
    """Used without a connected client: joining voice needs a gateway."""

    __slots__ = ()

    async def connect_voice(
        self, guild_id: int, channel_id: int, /, *, self_mute: bool, self_deaf: bool
    ) -> "VoiceClient":
        del guild_id, channel_id, self_mute, self_deaf
        what = "joining a voice channel"
        raise GatewayRequiredError(what)

    def voice_client(self, guild_id: int, /) -> "VoiceClient | None":
        del guild_id
        return None


@final
class _NoViews(ViewRegistry):
    """Used without a client: views are rendered, but nothing receives their interactions."""

    __slots__ = ()

    @override
    def store(self, view: ComponentView, *, message_id: int | None) -> None:
        del view, message_id


@final
class State:
    """The REST client, cache and identity that models act through.

    Args:
        rest: Every model method that calls Discord uses it.
        cache: Lookups such as `guild.get_member` and `member.roles` read it synchronously
            (`CacheStore.peek`); a model built from a REST answer still works with an empty cache.
        views: Where views sent with a message are kept; a `Client` passes its own.
        clock: What models wait and tell the time with (`delete_after`, typing, timeouts).
        member_requests: How `guild.chunk()` and `guild.query_members()` reach the gateway; a
            `Client` passes itself.
        voice: How `VoiceChannel.connect()` joins voice through the gateway; a `Client` passes itself.
    """

    __slots__ = ("_application_id", "_user_id", "cache", "clock", "member_requests", "rest", "views", "voice")

    def __init__(
        self,
        *,
        rest: RestClient,
        cache: CacheStore | None = None,
        views: ViewRegistry | None = None,
        clock: Clock | None = None,
        member_requests: MemberRequests | None = None,
        voice: "VoiceGateway | None" = None,
    ) -> None:
        """Create the state; see the class docstring for the arguments."""
        self.rest: RestClient = rest
        self.cache: CacheStore = cache or CacheStore()
        self.views: ViewRegistry = views or _NoViews()
        self.clock: Clock = clock or SystemClock()
        self.member_requests: MemberRequests = member_requests or _NoGateway()
        self.voice: VoiceGateway = voice or _NoVoice()
        self._user_id: Snowflake | None = None
        self._application_id: Snowflake | None = None

    def now(self) -> datetime:
        """The current time, from `clock`."""
        return datetime.fromtimestamp(self.clock.wall(), UTC)

    def delete_later(self, delay: float, delete: Callable[[], Awaitable[None]], *, name: str) -> None:
        """Run `delete` after `delay` seconds without waiting; something already gone is fine."""

        async def later() -> None:
            await self.clock.sleep(delay)
            try:
                await delete()
            except NotFoundError:
                _log.debug("%s: already deleted", name)

        _ = spawn(later(), name=name)

    @property
    def user_id(self) -> Snowflake | None:
        """The bot's user ID, once known (from `READY`, or set by whoever built the state)."""
        return self._user_id

    @property
    def application_id(self) -> Snowflake | None:
        """The bot's application ID, once known."""
        return self._application_id

    def using(self, cache: CacheStore) -> "State":
        """This state reading `cache` instead: for objects that outlive what the live cache holds."""
        other = State(
            rest=self.rest,
            cache=cache,
            views=self.views,
            clock=self.clock,
            member_requests=self.member_requests,
            voice=self.voice,
        )
        other._user_id = self._user_id
        other._application_id = self._application_id
        return other

    def identify(self, *, user_id: int, application_id: int) -> None:
        """Record who the bot is (the client does this on `READY`)."""
        self._user_id = Snowflake(user_id)
        self._application_id = Snowflake(application_id)
