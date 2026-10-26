"""Guild templates: a code that creates a guild from a snapshot of another.

Discord: https://docs.discord.com/developers/resources/guild-template
"""

from datetime import datetime

from msgspec import UNSET, UnsetType

from shoal.core.codec import JSONObject
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload
from shoal.payloads.user import User


class GuildTemplate(Payload):
    """A guild template.

    Discord: https://docs.discord.com/developers/resources/guild-template#guild-template-object
    """

    code: str
    name: str
    description: str | None
    usage_count: int
    creator_id: Snowflake
    creator: User
    created_at: datetime
    updated_at: datetime
    """When the template was last synced to its guild."""
    source_guild_id: Snowflake
    serialized_source_guild: JSONObject
    """The guild snapshot, kept as JSON: its IDs are placeholder integers rather than snowflakes, so
    it does not decode as a `Guild`."""
    is_dirty: bool | None
    """Whether the guild has changed since the last sync."""


class CreateGuildTemplateParams(Payload):
    """JSON body of Create Guild Template.

    Discord: https://docs.discord.com/developers/resources/guild-template#create-guild-template-json-params
    """

    name: str
    """1 to 100 characters."""
    description: str | UnsetType | None = UNSET
    """Up to 120 characters."""


class ModifyGuildTemplateParams(Payload):
    """JSON body of Modify Guild Template.

    Discord: https://docs.discord.com/developers/resources/guild-template#modify-guild-template-json-params
    """

    name: str | UnsetType = UNSET
    description: str | UnsetType | None = UNSET
