"""Endpoints for voice regions and voice states.

Discord: https://docs.discord.com/developers/resources/voice
"""

from shoal.payloads.voice import (
    ModifyCurrentUserVoiceStateParams,
    ModifyUserVoiceStateParams,
    VoiceRegion,
    VoiceState,
)
from shoal.rest.endpoints import (
    GET_CURRENT_USER_VOICE_STATE,
    GET_USER_VOICE_STATE,
    LIST_VOICE_REGIONS,
    MODIFY_CURRENT_USER_VOICE_STATE,
    MODIFY_USER_VOICE_STATE,
)
from shoal.rest.requester import Requester


class VoiceEndpoints(Requester):
    """Endpoints for voice regions and voice states; part of `RestClient`."""

    __slots__ = ()

    async def list_voice_regions(self) -> list[VoiceRegion]:
        """List the regions a voice or stage channel's `rtc_region` can be set to.

        Discord: https://docs.discord.com/developers/resources/voice#list-voice-regions
        """
        return await self.request(LIST_VOICE_REGIONS.compile(), list[VoiceRegion])

    async def get_current_user_voice_state(self, guild_id: int) -> VoiceState:
        """Get the current user's voice state in a guild.

        Discord: https://docs.discord.com/developers/resources/voice#get-current-user-voice-state
        """
        return await self.request(GET_CURRENT_USER_VOICE_STATE.compile(guild_id=guild_id), VoiceState)

    async def get_user_voice_state(self, guild_id: int, user_id: int) -> VoiceState:
        """Get a user's voice state in a guild. Needs Connect on their channel, if they are in one.

        Discord: https://docs.discord.com/developers/resources/voice#get-user-voice-state
        """
        return await self.request(
            GET_USER_VOICE_STATE.compile(guild_id=guild_id, user_id=user_id), VoiceState
        )

    async def modify_current_user_voice_state(
        self, guild_id: int, params: ModifyCurrentUserVoiceStateParams
    ) -> None:
        """Suppress or unsuppress the current user in a stage, or request to speak.

        Discord: https://docs.discord.com/developers/resources/voice#modify-current-user-voice-state
        """
        await self.request_empty(MODIFY_CURRENT_USER_VOICE_STATE.compile(guild_id=guild_id), body=params)

    async def modify_user_voice_state(
        self, guild_id: int, user_id: int, params: ModifyUserVoiceStateParams
    ) -> None:
        """Suppress or unsuppress another user in a stage. Needs Mute Members.

        Discord: https://docs.discord.com/developers/resources/voice#modify-user-voice-state
        """
        await self.request_empty(
            MODIFY_USER_VOICE_STATE.compile(guild_id=guild_id, user_id=user_id), body=params
        )
