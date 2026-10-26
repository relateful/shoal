"""Endpoints for stage instances.

Changing one needs to be a moderator of the stage: Manage Channels, Mute Members and Move Members.

Discord: https://docs.discord.com/developers/resources/stage-instance
"""

from shoal.payloads.stage_instance import CreateStageInstanceParams, EditStageInstanceParams, StageInstance
from shoal.rest.endpoints import (
    CREATE_STAGE_INSTANCE,
    DELETE_STAGE_INSTANCE,
    GET_STAGE_INSTANCE,
    MODIFY_STAGE_INSTANCE,
)
from shoal.rest.requester import Resource


class StageInstances(Resource):
    """Live stages.

    Use it as `rest.stage_instances`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def create(self, params: CreateStageInstanceParams, *, reason: str | None = None) -> StageInstance:
        """Make a stage channel live with a topic.

        Discord: https://docs.discord.com/developers/resources/stage-instance#create-stage-instance
        """
        return await self.request(CREATE_STAGE_INSTANCE.compile(), StageInstance, body=params, reason=reason)

    async def get(self, channel_id: int) -> StageInstance:
        """Get the live stage instance of a stage channel.

        Raises:
            NotFoundError: The stage is not live.

        Discord: https://docs.discord.com/developers/resources/stage-instance#get-stage-instance
        """
        return await self.request(GET_STAGE_INSTANCE.compile(channel_id=channel_id), StageInstance)

    async def edit(
        self, channel_id: int, params: EditStageInstanceParams, *, reason: str | None = None
    ) -> StageInstance:
        """Change a live stage's topic or privacy.

        Discord: https://docs.discord.com/developers/resources/stage-instance#modify-stage-instance
        """
        return await self.request(
            MODIFY_STAGE_INSTANCE.compile(channel_id=channel_id), StageInstance, body=params, reason=reason
        )

    async def delete(self, channel_id: int, *, reason: str | None = None) -> None:
        """End a live stage.

        Discord: https://docs.discord.com/developers/resources/stage-instance#delete-stage-instance
        """
        await self.request_empty(DELETE_STAGE_INSTANCE.compile(channel_id=channel_id), reason=reason)
