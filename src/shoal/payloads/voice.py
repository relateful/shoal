"""Voice states and voice regions.

Discord: https://docs.discord.com/developers/resources/voice
"""

from datetime import datetime

from msgspec import UNSET, UnsetType

from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload
from shoal.payloads.guild import GuildMember


class VoiceState(Payload):
    """A user's voice connection status in a guild.

    `guild_id` is absent on the voice states inside `GUILD_CREATE`, which all belong to that guild.

    Discord: https://docs.discord.com/developers/resources/voice#voice-state-object
    """

    guild_id: Snowflake | UnsetType = UNSET
    channel_id: Snowflake | None
    user_id: Snowflake
    member: GuildMember | UnsetType = UNSET
    session_id: str
    deaf: bool
    mute: bool
    self_deaf: bool
    self_mute: bool
    self_stream: bool | UnsetType = UNSET
    self_video: bool
    suppress: bool
    request_to_speak_timestamp: datetime | None


class VoiceRegion(Payload):
    """A region a voice or stage channel's `rtc_region` can be set to.

    Discord: https://docs.discord.com/developers/resources/voice#voice-region-object
    """

    id: str
    name: str
    optimal: bool
    """Whether this is the closest region to the current user's client."""
    deprecated: bool
    """Avoid switching to deprecated regions."""
    custom: bool
    """A custom region, used for events."""


class ModifyCurrentUserVoiceStateParams(Payload):
    """JSON body of Modify Current User Voice State. Only stage channels are supported.

    Discord: https://docs.discord.com/developers/resources/voice#modify-current-user-voice-state-json-params
    """

    channel_id: Snowflake | UnsetType = UNSET
    """A stage channel the current user has already joined."""
    suppress: bool | UnsetType = UNSET
    """Unsuppressing yourself needs Mute Members; suppressing yourself is always allowed."""
    request_to_speak_timestamp: datetime | UnsetType | None = UNSET
    """Any present or future time; needs Request to Speak, except to clear it."""


class ModifyUserVoiceStateParams(Payload):
    """JSON body of Modify User Voice State. Only stage channels are supported; needs Mute Members.

    Discord: https://docs.discord.com/developers/resources/voice#modify-user-voice-state-json-params
    """

    channel_id: Snowflake | UnsetType = UNSET
    """A stage channel the user has already joined."""
    suppress: bool | UnsetType = UNSET
