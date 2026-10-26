"""What every model holds: the REST client, the cache, and who the bot is.

`shoal.Client` creates one `State` and hands it to every model it builds, so `message.reply(...)`
sends through the client's REST client and `guild.get_member(...)` reads the client's cache. A
dashboard or worker without a `Client` can build one itself:

    state = State(rest=RestClient(token), cache=CacheStore())
    guild = Guild(state, await state.rest.guilds.get(guild_id))
"""

from typing import Protocol, final, override

from shoal.cache.store import CacheStore
from shoal.core.snowflake import Snowflake
from shoal.payloads.components import MessageComponent
from shoal.rest.client import RestClient


class ComponentView(Protocol):
    """Something that renders a message's components and wants their interactions: a `ui.View`."""

    def to_components(self) -> list[MessageComponent]:
        """The components to send."""
        ...

    def is_dispatchable(self) -> bool:
        """Whether interactions with these components should be routed back to it."""
        ...


class ViewRegistry(Protocol):
    """Where views are kept so component interactions reach them: the client's view store."""

    def store(self, view: ComponentView, *, message_id: int | None) -> None:
        """Route interactions with `view`'s components (on `message_id`, when known) to it."""
        ...


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
    """

    __slots__ = ("_application_id", "_user_id", "cache", "rest", "views")

    def __init__(
        self, *, rest: RestClient, cache: CacheStore | None = None, views: ViewRegistry | None = None
    ) -> None:
        """Create the state; see the class docstring for the arguments."""
        self.rest: RestClient = rest
        self.cache: CacheStore = cache or CacheStore()
        self.views: ViewRegistry = views or _NoViews()
        self._user_id: Snowflake | None = None
        self._application_id: Snowflake | None = None

    @property
    def user_id(self) -> Snowflake | None:
        """The bot's user ID, once known (from `READY`, or set by whoever built the state)."""
        return self._user_id

    @property
    def application_id(self) -> Snowflake | None:
        """The bot's application ID, once known."""
        return self._application_id

    def identify(self, *, user_id: int, application_id: int) -> None:
        """Record who the bot is (the client does this on `READY`)."""
        self._user_id = Snowflake(user_id)
        self._application_id = Snowflake(application_id)
