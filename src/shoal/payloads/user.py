"""Users and the objects nested in them.

Discord: https://docs.discord.com/developers/resources/user

Not yet modeled: `Connection.integrations` (partial guild integrations). Decoding ignores it until
it is added.
"""

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum, DiscordStrEnum
from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.api import ImageData
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

    REDACTED_FIELDS = frozenset({"email"})

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


class ConnectionService(DiscordStrEnum):
    """The service an account connection links to.

    Discord: https://docs.discord.com/developers/resources/user#connection-object-services
    """

    AMAZON_MUSIC = "amazon-music"
    BLUESKY = "bluesky"
    BUNGIE = "bungie"
    CRUNCHYROLL = "crunchyroll"
    DOMAIN = "domain"
    EBAY = "ebay"
    EPIC_GAMES = "epicgames"
    FACEBOOK = "facebook"
    GITHUB = "github"
    INSTAGRAM = "instagram"
    """No longer available for new connections."""
    MASTODON = "mastodon"
    PAYPAL = "paypal"
    PLAYSTATION = "playstation"
    REDDIT = "reddit"
    ROBLOX = "roblox"
    SKYPE = "skype"
    """No longer available for new connections."""
    SPOTIFY = "spotify"
    STEAM = "steam"
    TIKTOK = "tiktok"
    TWITCH = "twitch"
    TWITTER = "twitter"
    XBOX = "xbox"
    YOUTUBE = "youtube"


class ConnectionVisibility(DiscordIntEnum):
    """Who can see an account connection.

    Discord: https://docs.discord.com/developers/resources/user#connection-object-visibility-types
    """

    NONE = 0
    """Only the user."""
    EVERYONE = 1


class Connection(Payload):
    """An account on another service that a user has connected. Needs the `connections` scope.

    Discord: https://docs.discord.com/developers/resources/user#connection-object
    """

    id: str
    name: str
    type: ConnectionService
    revoked: bool | UnsetType = UNSET
    verified: bool
    friend_sync: bool
    show_activity: bool
    two_way_link: bool
    visibility: ConnectionVisibility


class ApplicationRoleConnection(Payload):
    """What an app has recorded about a user, which linked roles check against.

    Discord: https://docs.discord.com/developers/resources/user#application-role-connection-object
    """

    platform_name: str | UnsetType | None = UNSET
    """Up to 50 characters."""
    platform_username: str | UnsetType | None = UNSET
    """The user's name on the platform, up to 100 characters."""
    metadata: dict[str, str] | UnsetType = UNSET
    """Values by metadata key, each up to 100 characters."""


class EditCurrentUserParams(Payload):
    """JSON body of Modify Current User.

    Discord: https://docs.discord.com/developers/resources/user#modify-current-user-json-params
    """

    username: str | UnsetType = UNSET
    """Changing it may change the discriminator."""
    avatar: ImageData | UnsetType | None = UNSET
    banner: ImageData | UnsetType | None = UNSET


class ListGuildsParams(Payload):
    """Query of Get Current User Guilds.

    Discord: https://docs.discord.com/developers/resources/user#get-current-user-guilds-query-string-params
    """

    before: Snowflake | UnsetType = UNSET
    after: Snowflake | UnsetType = UNSET
    limit: int | UnsetType = UNSET
    """1 to 200; Discord's default is 200."""
    shard: int | UnsetType = UNSET
    """Required for large bot sharding: `0` to `max_concurrency - 1`, not the gateway shard ID."""
    with_counts: bool | UnsetType = UNSET


class CreateDMParams(Payload):
    """JSON body of Create DM.

    Discord: https://docs.discord.com/developers/resources/user#create-dm-json-params
    """

    recipient_id: Snowflake


class CreateGroupDMParams(Payload):
    """JSON body of Create Group DM.

    Discord: https://docs.discord.com/developers/resources/user#create-group-dm-json-params
    """

    REDACTED_FIELDS = frozenset({"access_tokens"})

    access_tokens: list[str]
    """OAuth2 tokens of users who granted the app the `gdm.join` scope."""
    nicks: dict[Snowflake, str]
    """Nicknames by user ID."""


class EditCurrentRoleConnectionParams(Payload):
    """JSON body of Update Current User Application Role Connection.

    Discord: https://docs.discord.com/developers/resources/user#update-current-user-application-role-connection-json-params
    """

    platform_name: str | UnsetType = UNSET
    """Up to 50 characters."""
    platform_username: str | UnsetType = UNSET
    """Up to 100 characters."""
    metadata: dict[str, str] | UnsetType = UNSET
    """Values by metadata key, each up to 100 characters."""
