"""Voice states.

Discord: https://docs.discord.com/developers/resources/voice

Not yet modeled: voice regions.
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
