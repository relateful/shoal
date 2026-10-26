"""Endpoints for soundboard sounds.

Discord: https://docs.discord.com/developers/resources/soundboard
"""

from shoal.payloads.soundboard import (
    CreateGuildSoundboardSoundParams,
    GuildSoundboardSounds,
    ModifyGuildSoundboardSoundParams,
    SendSoundboardSoundParams,
    SoundboardSound,
)
from shoal.rest.endpoints import (
    CREATE_GUILD_SOUNDBOARD_SOUND,
    DELETE_GUILD_SOUNDBOARD_SOUND,
    GET_GUILD_SOUNDBOARD_SOUND,
    LIST_DEFAULT_SOUNDBOARD_SOUNDS,
    LIST_GUILD_SOUNDBOARD_SOUNDS,
    MODIFY_GUILD_SOUNDBOARD_SOUND,
    SEND_SOUNDBOARD_SOUND,
)
from shoal.rest.requester import Requester


class SoundboardEndpoints(Requester):
    """Endpoints for soundboard sounds; part of `RestClient`."""

    __slots__ = ()

    async def send_soundboard_sound(self, channel_id: int, params: SendSoundboardSoundParams) -> None:
        """Play a sound in the voice channel the current user is connected to.

        Needs Speak and Use Soundboard (and Use External Sounds for another guild's sound), and a
        voice state that is not deafened, muted or suppressed.

        Discord: https://docs.discord.com/developers/resources/soundboard#send-soundboard-sound
        """
        await self.request_empty(SEND_SOUNDBOARD_SOUND.compile(channel_id=channel_id), body=params)

    async def list_default_soundboard_sounds(self) -> list[SoundboardSound]:
        """List the sounds every user can play.

        Discord: https://docs.discord.com/developers/resources/soundboard#list-default-soundboard-sounds
        """
        return await self.request(LIST_DEFAULT_SOUNDBOARD_SOUNDS.compile(), list[SoundboardSound])

    async def list_guild_soundboard_sounds(self, guild_id: int) -> list[SoundboardSound]:
        """List a guild's sounds. `user` is set with Create or Manage Expressions.

        Discord: https://docs.discord.com/developers/resources/soundboard#list-guild-soundboard-sounds
        """
        response = await self.request(
            LIST_GUILD_SOUNDBOARD_SOUNDS.compile(guild_id=guild_id), GuildSoundboardSounds
        )
        return response.items

    async def get_guild_soundboard_sound(self, guild_id: int, sound_id: int) -> SoundboardSound:
        """Get one of a guild's sounds.

        Discord: https://docs.discord.com/developers/resources/soundboard#get-guild-soundboard-sound
        """
        return await self.request(
            GET_GUILD_SOUNDBOARD_SOUND.compile(guild_id=guild_id, sound_id=sound_id), SoundboardSound
        )

    async def create_guild_soundboard_sound(
        self, guild_id: int, params: CreateGuildSoundboardSoundParams, *, reason: str | None = None
    ) -> SoundboardSound:
        """Add a sound to a guild. Needs Create Expressions.

        Discord: https://docs.discord.com/developers/resources/soundboard#create-guild-soundboard-sound
        """
        return await self.request(
            CREATE_GUILD_SOUNDBOARD_SOUND.compile(guild_id=guild_id),
            SoundboardSound,
            body=params,
            reason=reason,
        )

    async def modify_guild_soundboard_sound(
        self,
        guild_id: int,
        sound_id: int,
        params: ModifyGuildSoundboardSoundParams,
        *,
        reason: str | None = None,
    ) -> SoundboardSound:
        """Change a sound's name, volume or emoji.

        Needs Manage Expressions, or Create Expressions for sounds the bot created.

        Discord: https://docs.discord.com/developers/resources/soundboard#modify-guild-soundboard-sound
        """
        return await self.request(
            MODIFY_GUILD_SOUNDBOARD_SOUND.compile(guild_id=guild_id, sound_id=sound_id),
            SoundboardSound,
            body=params,
            reason=reason,
        )

    async def delete_guild_soundboard_sound(
        self, guild_id: int, sound_id: int, *, reason: str | None = None
    ) -> None:
        """Delete a guild's sound.

        Needs Manage Expressions, or Create Expressions for sounds the bot created.

        Discord: https://docs.discord.com/developers/resources/soundboard#delete-guild-soundboard-sound
        """
        await self.request_empty(
            DELETE_GUILD_SOUNDBOARD_SOUND.compile(guild_id=guild_id, sound_id=sound_id), reason=reason
        )
