"""Images on Discord's CDN: avatars, icons, banners, emojis and stickers.

    user.display_avatar.url                       # https://cdn.discordapp.com/avatars/.../....png
    guild.icon.with_size(256).url if guild.icon else None

Discord: https://docs.discord.com/developers/reference#image-formatting
"""

from typing import Literal, Self, final, override

from shoal.payloads.api import CDN_BASE_URL, CDN_IMAGE_MAX_SIZE, CDN_IMAGE_MIN_SIZE

type ImageFormat = Literal["png", "jpg", "jpeg", "webp", "gif", "json"]
"""An image file extension Discord's CDN serves.

Discord: https://docs.discord.com/developers/reference#image-formatting-image-formats
"""


@final
class Asset:
    """One image on Discord's CDN, with a format and an optional size.

    Animated images (their hash starts with `a_`) are served as animated WebP by default, which
    Discord recommends because it works whatever format was uploaded; ask for `with_format("gif")`
    when you need a GIF. Static images default to PNG.

    Discord: https://docs.discord.com/developers/reference#image-formatting
    """

    __slots__ = ("_animated", "_format", "_key", "_path", "_sizable", "_size")

    def __init__(
        self,
        path: str,
        key: str,
        *,
        animated: bool = False,
        image_format: ImageFormat | None = None,
        size: int | None = None,
        sizable: bool = True,
    ) -> None:
        """An asset at `CDN_BASE_URL/<path>.<format>`; prefer the `for_*` constructors."""
        self._path: str = path
        self._key: str = key
        self._animated: bool = animated
        self._format: ImageFormat = image_format or ("webp" if animated else "png")
        self._size: int | None = size
        self._sizable: bool = sizable

    @classmethod
    def for_avatar(cls, user_id: int, avatar: str) -> Self:
        """A user's avatar."""
        return cls(f"avatars/{user_id}/{avatar}", avatar, animated=avatar.startswith("a_"))

    @classmethod
    def for_default_avatar(cls, user_id: int, discriminator: str) -> Self:
        """The avatar Discord shows for a user who has not set one.

        Users on the new username system (discriminator `0`) get `(id >> 22) % 6`; legacy users get
        their discriminator modulo 5.
        """
        index = (user_id >> 22) % 6 if discriminator in {"", "0"} else int(discriminator) % 5
        return cls(f"embed/avatars/{index}", str(index), sizable=False)

    @classmethod
    def for_member_avatar(cls, guild_id: int, user_id: int, avatar: str) -> Self:
        """A member's avatar for one guild."""
        return cls(
            f"guilds/{guild_id}/users/{user_id}/avatars/{avatar}", avatar, animated=avatar.startswith("a_")
        )

    @classmethod
    def for_banner(cls, owner_id: int, banner: str) -> Self:
        """A user's or a guild's banner."""
        return cls(f"banners/{owner_id}/{banner}", banner, animated=banner.startswith("a_"))

    @classmethod
    def for_member_banner(cls, guild_id: int, user_id: int, banner: str) -> Self:
        """A member's banner for one guild."""
        return cls(
            f"guilds/{guild_id}/users/{user_id}/banners/{banner}", banner, animated=banner.startswith("a_")
        )

    @classmethod
    def for_guild_icon(cls, guild_id: int, icon: str) -> Self:
        """A guild's icon."""
        return cls(f"icons/{guild_id}/{icon}", icon, animated=icon.startswith("a_"))

    @classmethod
    def for_guild_splash(cls, guild_id: int, splash: str) -> Self:
        """A guild's invite splash."""
        return cls(f"splashes/{guild_id}/{splash}", splash)

    @classmethod
    def for_discovery_splash(cls, guild_id: int, splash: str) -> Self:
        """A guild's discovery splash."""
        return cls(f"discovery-splashes/{guild_id}/{splash}", splash)

    @classmethod
    def for_role_icon(cls, role_id: int, icon: str) -> Self:
        """A role's icon."""
        return cls(f"role-icons/{role_id}/{icon}", icon)

    @classmethod
    def for_emoji(cls, emoji_id: int, *, animated: bool = False) -> Self:
        """A custom emoji; Discord recommends WebP for every emoji."""
        return cls(f"emojis/{emoji_id}", str(emoji_id), animated=animated, image_format="webp")

    @classmethod
    def for_scheduled_event_cover(cls, event_id: int, image: str) -> Self:
        """A scheduled event's cover image."""
        return cls(f"guild-events/{event_id}/{image}", image)

    @property
    def key(self) -> str:
        """The image's hash (or ID, for emojis and default avatars)."""
        return self._key

    @property
    def url(self) -> str:
        """The URL of the image in its format and size."""
        query: list[str] = []
        if self._size is not None and self._sizable:
            query.append(f"size={self._size}")
        if self._animated and self._format == "webp":
            query.append("animated=true")
        suffix = f"?{'&'.join(query)}" if query else ""
        return f"{CDN_BASE_URL}/{self._path}.{self._format}{suffix}"

    def is_animated(self) -> bool:
        """Whether the image is animated."""
        return self._animated

    def with_size(self, size: int) -> Self:
        """The same image at `size` pixels, a power of two from 16 to 4096.

        Raises:
            ValueError: `size` is not such a power of two.
        """
        if not CDN_IMAGE_MIN_SIZE <= size <= CDN_IMAGE_MAX_SIZE or size & (size - 1):
            msg = f"size must be a power of two from {CDN_IMAGE_MIN_SIZE} to {CDN_IMAGE_MAX_SIZE}, not {size}"
            raise ValueError(msg)
        return self._copy(self._format, size)

    def with_format(self, image_format: ImageFormat) -> Self:
        """The same image in another format.

        Raises:
            ValueError: A static image cannot be served as a GIF.
        """
        if image_format == "gif" and not self._animated:
            msg = "only animated images can be served as GIF"
            raise ValueError(msg)
        return self._copy(image_format, self._size)

    def with_static_format(self, image_format: ImageFormat) -> Self:
        """`with_format` for a static image; an animated one keeps its format."""
        return self if self._animated else self.with_format(image_format)

    def _copy(self, image_format: ImageFormat, size: int | None) -> Self:
        return type(self)(
            self._path,
            self._key,
            animated=self._animated,
            image_format=image_format,
            size=size,
            sizable=self._sizable,
        )

    @override
    def __str__(self) -> str:
        return self.url

    @override
    def __repr__(self) -> str:
        return f"<Asset url={self.url!r}>"

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Asset) and other.url == self.url

    @override
    def __hash__(self) -> int:
        return hash(self.url)
