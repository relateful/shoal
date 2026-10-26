"""Soundboard sounds.

Discord: https://docs.discord.com/developers/resources/soundboard
"""

from msgspec import UNSET, UnsetType

from shoal.core.snowflake import Snowflake
from shoal.payloads.api import SoundData
from shoal.payloads.base import Payload
from shoal.payloads.user import User


class SoundboardSound(Payload):
    """A sound users can play in voice channels.

    Discord: https://docs.discord.com/developers/resources/soundboard#soundboard-sound-object
    """

    name: str
    sound_id: Snowflake
    volume: float
    """From 0 to 1."""
    emoji_id: Snowflake | None
    """The sound's custom emoji."""
    emoji_name: str | None
    """The sound's standard emoji, as its unicode character."""
    guild_id: Snowflake | UnsetType = UNSET
    available: bool
    """`False` after the guild loses the Boosts it needed."""
    user: User | UnsetType = UNSET
    """Who created the sound; needs Create or Manage Expressions."""


class GuildSoundboardSounds(Payload):
    """The response of List Guild Soundboard Sounds.

    Discord: https://docs.discord.com/developers/resources/soundboard#list-guild-soundboard-sounds-response-structure
    """

    items: list[SoundboardSound]


class SendSoundboardSoundParams(Payload):
    """JSON body of Send Soundboard Sound.

    Discord: https://docs.discord.com/developers/resources/soundboard#send-soundboard-sound-json-params
    """

    sound_id: Snowflake
    source_guild_id: Snowflake | UnsetType = UNSET
    """Required for a sound from another guild."""


class CreateSoundboardSoundParams(Payload):
    """JSON body of Create Guild Soundboard Sound. The sound may be at most 512 KB and 5.2 seconds.

    Discord: https://docs.discord.com/developers/resources/soundboard#create-guild-soundboard-sound-json-params
    """

    name: str
    """2 to 32 characters."""
    sound: SoundData
    volume: float | UnsetType | None = UNSET
    """From 0 to 1; Discord's default is 1."""
    emoji_id: Snowflake | UnsetType | None = UNSET
    emoji_name: str | UnsetType | None = UNSET


class EditSoundboardSoundParams(Payload):
    """JSON body of Modify Guild Soundboard Sound.

    Discord: https://docs.discord.com/developers/resources/soundboard#modify-guild-soundboard-sound-json-params
    """

    name: str | UnsetType = UNSET
    """2 to 32 characters."""
    volume: float | UnsetType | None = UNSET
    emoji_id: Snowflake | UnsetType | None = UNSET
    emoji_name: str | UnsetType | None = UNSET
