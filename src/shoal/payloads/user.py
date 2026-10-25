"""Users and the objects nested in them.

Discord: https://docs.discord.com/developers/resources/user

Not yet modeled: the connection and application role connection objects (OAuth2-only).
"""

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum
from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload


class UserFlags(BaseFlags):
    """Badges and account flags on a user.

    Discord: https://docs.discord.com/developers/resources/user#user-object-user-flags
    """

    __slots__ = ()

    staff = flag(0)
    partner = flag(1)
    hypesquad = flag(2)
    bug_hunter_level_1 = flag(3)
    hypesquad_online_house_1 = flag(6)
    hypesquad_online_house_2 = flag(7)
    hypesquad_online_house_3 = flag(8)
    premium_early_supporter = flag(9)
    team_pseudo_user = flag(10)
    bug_hunter_level_2 = flag(14)
    verified_bot = flag(16)
    verified_developer = flag(17)
    certified_moderator = flag(18)
    bot_http_interactions = flag(19)


class PremiumType(DiscordIntEnum):
    """The Nitro subscription on an account.

    Discord: https://docs.discord.com/developers/resources/user#user-object-premium-types
    """

    NONE = 0
    NITRO_CLASSIC = 1
    NITRO = 2
    NITRO_BASIC = 3


class AvatarDecorationData(Payload):
    """The avatar decoration a user or member is wearing.

    Discord: https://docs.discord.com/developers/resources/user#avatar-decoration-data-object
    """

    asset: str
    sku_id: Snowflake


class Nameplate(Payload):
    """A nameplate collectible.

    Discord: https://docs.discord.com/developers/resources/user#nameplate-nameplate-structure
    """

    sku_id: Snowflake
    asset: str
    label: str
    palette: str


class Collectibles(Payload):
    """Collectibles a user has equipped.

    Discord: https://docs.discord.com/developers/resources/user#collectibles-collectible-structure
    """

    nameplate: Nameplate | UnsetType = UNSET


class UserPrimaryGuild(Payload):
    """The server tag a user displays.

    Discord: https://docs.discord.com/developers/resources/user#user-object-user-primary-guild
    """

    identity_guild_id: Snowflake | None
    identity_enabled: bool | None
    tag: str | None
    badge: str | None


class User(Payload):
    """A Discord user.

    Discord: https://docs.discord.com/developers/resources/user#user-object
    """

    id: Snowflake
    username: str
    discriminator: str
    global_name: str | None
    avatar: str | None
    bot: bool | UnsetType = UNSET
    system: bool | UnsetType = UNSET
    mfa_enabled: bool | UnsetType = UNSET
    banner: str | UnsetType | None = UNSET
    accent_color: int | UnsetType | None = UNSET
    locale: str | UnsetType = UNSET
    verified: bool | UnsetType = UNSET
    email: str | UnsetType | None = UNSET
    flags: UserFlags | UnsetType = UNSET
    premium_type: PremiumType | UnsetType = UNSET
    public_flags: UserFlags | UnsetType = UNSET
    avatar_decoration_data: AvatarDecorationData | UnsetType | None = UNSET
    collectibles: Collectibles | UnsetType | None = UNSET
    primary_guild: UserPrimaryGuild | UnsetType | None = UNSET
