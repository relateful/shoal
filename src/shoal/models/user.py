"""Users: anyone on Discord, and the bot itself.

    await user.send("Your report was received.")
    user.display_avatar.url

Discord: https://docs.discord.com/developers/resources/user#user-object
"""

from typing import TYPE_CHECKING, Self, override

from shoal.core.snowflake import Snowflake
from shoal.models.asset import Asset
from shoal.models.base import MISSING, Hashable, MissingType, given
from shoal.models.messageable import Messageable
from shoal.models.state import State
from shoal.payloads.api import image_data
from shoal.payloads.user import EditCurrentUserParams, UserFlags
from shoal.payloads.user import User as UserPayload

if TYPE_CHECKING:
    from shoal.models.channel import DMChannel
    from shoal.models.message import Message


class BaseUser(Hashable):
    """What `User`, `ClientUser` and `Member` share about the person behind them.

    Discord: https://docs.discord.com/developers/resources/user#user-object
    """

    __slots__ = ()

    @property
    def _user_data(self) -> UserPayload:
        raise NotImplementedError

    @property
    @override
    def id(self) -> Snowflake:
        return self._user_data.id

    @property
    def name(self) -> str:
        """The unique username."""
        return self._user_data.username

    @property
    def global_name(self) -> str | None:
        """The display name the user chose, if any."""
        return self._user_data.global_name

    @property
    def display_name(self) -> str:
        """The name Discord shows: the global name, or the username."""
        return self._user_data.global_name or self._user_data.username

    @property
    def discriminator(self) -> str:
        """`"0"` for users on the new username system; the legacy four digits otherwise."""
        return self._user_data.discriminator

    @property
    def bot(self) -> bool:
        """Whether this is a bot account."""
        return self._user_data.bot is True

    @property
    def system(self) -> bool:
        """Whether this is Discord's official system account."""
        return self._user_data.system is True

    @property
    def avatar(self) -> Asset | None:
        """The avatar the user uploaded, if any."""
        avatar = self._user_data.avatar
        return Asset.for_avatar(self.id, avatar) if avatar else None

    @property
    def default_avatar(self) -> Asset:
        """The avatar Discord shows when the user has none."""
        return Asset.for_default_avatar(self.id, self.discriminator)

    @property
    def display_avatar(self) -> Asset:
        """The avatar Discord shows: the uploaded one, or the default."""
        return self.avatar or self.default_avatar

    @property
    def banner(self) -> Asset | None:
        """The profile banner, when Discord sent it (Get User does)."""
        banner = self._user_data.banner
        return Asset.for_banner(self.id, banner) if isinstance(banner, str) else None

    @property
    def accent_colour(self) -> int | None:
        """The profile accent colour, when Discord sent it."""
        colour = self._user_data.accent_color
        return colour if isinstance(colour, int) else None

    accent_color = accent_colour

    @property
    def public_flags(self) -> UserFlags:
        """The badges on the user's profile."""
        flags = self._user_data.public_flags
        return flags if isinstance(flags, UserFlags) else UserFlags.none()

    @property
    def mention(self) -> str:
        """`<@id>`, which Discord renders as a mention."""
        return f"<@{int(self.id)}>"

    def mentioned_in(self, message: "Message") -> bool:
        """Whether `message` mentions this user (directly, or through @everyone)."""
        return message.mention_everyone or self.id in message.raw_mentions

    @override
    def __str__(self) -> str:
        if self.discriminator in {"", "0"}:
            return self.name
        return f"{self.name}#{self.discriminator}"


class User(BaseUser, Messageable):
    """A Discord user, outside any guild. `send` opens a DM with them.

    Discord: https://docs.discord.com/developers/resources/user#user-object
    """

    __slots__ = ("_data", "_state")

    def __init__(self, state: State, data: UserPayload) -> None:
        """A user from their payload."""
        self._state: State = state
        self._data: UserPayload = data

    @classmethod
    def from_cache(cls, state: State, user_id: int) -> Self | None:
        """The cached user with this ID."""
        data = state.cache.peek(state.cache.users, Snowflake(user_id))
        return cls(state, data) if data is not None else None

    @property
    @override
    def _user_data(self) -> UserPayload:
        return self._data

    @property
    @override
    def _messageable_state(self) -> State:
        return self._state

    @override
    async def _messageable_channel(self) -> tuple[Snowflake, Snowflake | None]:
        return (await self.create_dm()).id, None

    @property
    def payload(self) -> UserPayload:
        """The user as Discord sent them."""
        return self._data

    async def create_dm(self) -> "DMChannel":
        """Open (or reuse) the DM channel with this user.

        Discord: https://docs.discord.com/developers/resources/user#create-dm
        """
        from shoal.models.channel import DMChannel

        return DMChannel(self._state, await self._state.rest.users.create_dm(self.id))

    @override
    def __repr__(self) -> str:
        return f"<User id={int(self.id)} name={self.name!r} bot={self.bot}>"


class ClientUser(User):
    """The bot's own user, with what only it can change.

    Discord: https://docs.discord.com/developers/resources/user#get-current-user
    """

    __slots__ = ()

    @property
    def verified(self) -> bool:
        """Whether the bot's email is verified."""
        return self._data.verified is True

    @property
    def mfa_enabled(self) -> bool:
        """Whether the bot's owner has two-factor authentication on the account."""
        return self._data.mfa_enabled is True

    async def edit(
        self,
        *,
        username: str | MissingType = MISSING,
        avatar: bytes | MissingType | None = MISSING,
        banner: bytes | MissingType | None = MISSING,
    ) -> "ClientUser":
        """Change the bot's username, avatar or banner (`None` removes the image); returns itself.

        `client.user` is this object, so it shows the change at once.

        Raises:
            ValueError: An image is not a PNG, JPEG or GIF.

        Discord: https://docs.discord.com/developers/resources/user#modify-current-user
        """
        params = EditCurrentUserParams(
            username=given(username),
            avatar=given(avatar) if not isinstance(avatar, bytes) else image_data(avatar),
            banner=given(banner) if not isinstance(banner, bytes) else image_data(banner),
        )
        self.refresh(await self._state.rest.users.edit_me(params))
        return self

    def refresh(self, data: UserPayload) -> None:
        """Show `data`, a newer copy of the bot's user (from `USER_UPDATE` or an edit)."""
        self._data = data

    @override
    def __repr__(self) -> str:
        return f"<ClientUser id={int(self.id)} name={self.name!r}>"
