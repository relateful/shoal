"""Application identity profiles: game stats a game stores for its players.

Game Stats Widgets show them on the players' Discord profiles.

Discord: https://docs.discord.com/developers/resources/application-identity-profile
"""

from msgspec import UNSET, UnsetType

from shoal.core.codec import JSONObject
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload


class ApplicationIdentity(Payload):
    """A link between a Discord user and their account in a game.

    Discord: https://docs.discord.com/developers/resources/application-identity-profile#application-identity-object
    """

    user_id: Snowflake | UnsetType = UNSET
    """In the identity listings; Discord's table leaves it out, its examples include it."""
    provider_type: str
    provider_id: str | UnsetType = UNSET
    """Left out when empty."""
    provider_issued_user_id: str
    """The player's ID in the game's system."""


class ApplicationIdentities(Payload):
    """The response of the identity listings.

    Discord: https://docs.discord.com/developers/resources/application-identity-profile#get-application-identities-by-user-id
    """

    identities: list[ApplicationIdentity]


class Media(Payload):
    """An image shown in a game stats widget, at a URL Discord's servers can reach.

    Discord: https://docs.discord.com/developers/resources/application-identity-profile#media-object
    """

    url: str


class PrimaryProfileData(Payload):
    """Stats most games share. Text values take up to 100 characters.

    Discord: https://docs.discord.com/developers/resources/application-identity-profile#primary-profile-data-object
    """

    season: str | UnsetType = UNSET
    rank_name: str | UnsetType = UNSET
    rank_image: Media | UnsetType = UNSET
    highest_rank: str | UnsetType = UNSET
    highest_rank_image: Media | UnsetType = UNSET
    featured_played_character: str | UnsetType = UNSET
    featured_played_character_image: Media | UnsetType = UNSET
    playtime_hours: float | UnsetType = UNSET
    total_wins: int | UnsetType = UNSET
    current_period_wins: int | UnsetType = UNSET
    total_games: int | UnsetType = UNSET
    current_period_games: int | UnsetType = UNSET
    total_kills: int | UnsetType = UNSET
    current_period_kills: int | UnsetType = UNSET
    total_assists: int | UnsetType = UNSET
    current_period_assists: int | UnsetType = UNSET
    total_deaths: int | UnsetType = UNSET
    current_period_deaths: int | UnsetType = UNSET


class DynamicStringField(Payload, tag=1, tag_field="type"):
    """A custom text stat.

    Discord: https://docs.discord.com/developers/resources/application-identity-profile#dynamic-field-object-dynamic-string-field-structure
    """

    name: str
    """The key the widget editor refers to, up to 100 characters; not shown to players."""
    value: str


class DynamicNumberField(Payload, tag=2, tag_field="type"):
    """A custom numeric stat.

    Discord: https://docs.discord.com/developers/resources/application-identity-profile#dynamic-field-object-dynamic-number-field-structure
    """

    name: str
    value: float


class DynamicMediaField(Payload, tag=3, tag_field="type"):
    """A custom image stat.

    Discord: https://docs.discord.com/developers/resources/application-identity-profile#dynamic-field-object-dynamic-media-field-structure
    """

    name: str
    value: Media


type DynamicField = DynamicStringField | DynamicNumberField | DynamicMediaField
"""A custom stat; its `type` decides the kind of value.

Discord: https://docs.discord.com/developers/resources/application-identity-profile#dynamic-field-object
"""


class ProfileData(Payload):
    """A player's game stats. The serialized object may be at most 10 KB.

    Discord: https://docs.discord.com/developers/resources/application-identity-profile#profile-data-object
    """

    primary: PrimaryProfileData | UnsetType = UNSET
    dynamic: list[DynamicField] | UnsetType = UNSET
    """Up to 30."""


class ApplicationIdentityProfile(Payload):
    """The game data stored on a player's application identity.

    Discord: https://docs.discord.com/developers/resources/application-identity-profile#application-identity-profile-object
    """

    username: str | None
    metadata: JSONObject | None
    """The game's own data, which Discord stores without reading."""
    data: ProfileData | None


class UpdateApplicationIdentityProfileParams(Payload):
    """JSON body of Update Application Identity Profile. `data`, when given, replaces all stats.

    Discord: https://docs.discord.com/developers/resources/application-identity-profile#update-application-identity-profile
    """

    username: str | UnsetType = UNSET
    """Up to 1024 characters."""
    data: ProfileData | UnsetType = UNSET


class DeleteApplicationIdentityParams(Payload):
    """JSON body of Delete Application Identity.

    Discord: https://docs.discord.com/developers/resources/application-identity-profile#delete-application-identity
    """

    provider_id: str | UnsetType = UNSET
