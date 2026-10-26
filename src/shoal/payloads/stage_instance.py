"""Stage instances: a live stage and its topic.

Discord: https://docs.discord.com/developers/resources/stage-instance
"""

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload


class StagePrivacyLevel(DiscordIntEnum):
    """Who can see a stage instance.

    Discord: https://docs.discord.com/developers/resources/stage-instance#stage-instance-object-privacy-level
    """

    PUBLIC = 1
    """Deprecated."""
    GUILD_ONLY = 2


class StageInstance(Payload):
    """A stage channel that is live, and its topic.

    Discord: https://docs.discord.com/developers/resources/stage-instance#stage-instance-object
    """

    id: Snowflake
    guild_id: Snowflake
    channel_id: Snowflake
    topic: str
    """1 to 120 characters."""
    privacy_level: StagePrivacyLevel
    discoverable_disabled: bool
    """Deprecated."""
    guild_scheduled_event_id: Snowflake | None


class CreateStageInstanceParams(Payload):
    """JSON body of Create Stage Instance. Needs to be a moderator of the stage.

    Discord: https://docs.discord.com/developers/resources/stage-instance#create-stage-instance-json-params
    """

    channel_id: Snowflake
    topic: str
    """1 to 120 characters."""
    privacy_level: StagePrivacyLevel | UnsetType = UNSET
    """Discord's default is `GUILD_ONLY`."""
    send_start_notification: bool | UnsetType = UNSET
    """Notify @everyone; needs Mention Everyone."""
    guild_scheduled_event_id: Snowflake | UnsetType = UNSET


class ModifyStageInstanceParams(Payload):
    """JSON body of Modify Stage Instance.

    Discord: https://docs.discord.com/developers/resources/stage-instance#modify-stage-instance-json-params
    """

    topic: str | UnsetType = UNSET
    privacy_level: StagePrivacyLevel | UnsetType = UNSET
