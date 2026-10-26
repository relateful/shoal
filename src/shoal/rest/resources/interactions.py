"""Endpoints for interaction responses and follow-up messages.

Discord: https://docs.discord.com/developers/interactions/receiving-and-responding
"""

from collections.abc import Sequence
from typing import Literal, overload

import msgspec

from shoal.payloads.interactions import (
    CreateFollowupMessageParams,
    InteractionCallbackResponse,
    InteractionResponse,
    MessageResponse,
    UpdateMessageResponse,
)
from shoal.payloads.message import (
    Message,
)
from shoal.payloads.webhook import EditWebhookMessageParams
from shoal.rest.endpoints import (
    CREATE_FOLLOWUP_MESSAGE,
    CREATE_INTERACTION_RESPONSE,
    DELETE_FOLLOWUP_MESSAGE,
    DELETE_ORIGINAL_INTERACTION_RESPONSE,
    EDIT_FOLLOWUP_MESSAGE,
    EDIT_ORIGINAL_INTERACTION_RESPONSE,
    GET_FOLLOWUP_MESSAGE,
    GET_ORIGINAL_INTERACTION_RESPONSE,
)
from shoal.rest.files import File
from shoal.rest.requester import Requester, with_attachments


class InteractionEndpoints(Requester):
    """Endpoints for interaction responses and follow-up messages; part of `RestClient`."""

    __slots__ = ()

    @overload
    async def create_interaction_response(
        self,
        interaction_id: int,
        interaction_token: str,
        response: InteractionResponse,
        *,
        with_response: Literal[False] = False,
        files: Sequence[File] = (),
    ) -> None: ...

    @overload
    async def create_interaction_response(
        self,
        interaction_id: int,
        interaction_token: str,
        response: InteractionResponse,
        *,
        with_response: Literal[True],
        files: Sequence[File] = (),
    ) -> InteractionCallbackResponse: ...

    @overload
    async def create_interaction_response(
        self,
        interaction_id: int,
        interaction_token: str,
        response: InteractionResponse,
        *,
        with_response: bool,
        files: Sequence[File] = (),
    ) -> InteractionCallbackResponse | None: ...

    async def create_interaction_response(
        self,
        interaction_id: int,
        interaction_token: str,
        response: InteractionResponse,
        *,
        with_response: bool = False,
        files: Sequence[File] = (),
    ) -> InteractionCallbackResponse | None:
        """Answer an interaction. Must happen within 3 seconds of receiving it, and only once.

        With `with_response`, Discord returns what the response created (the message, or the
        launched Activity). `files` can go with a message response or an update of the message.

        Raises:
            TypeError: `files` were given with a response that carries no message.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#create-interaction-response
        """
        route = CREATE_INTERACTION_RESPONSE.compile(
            interaction_id=interaction_id, interaction_token=interaction_token
        )
        body, named = _response_with_files(response, files)
        if with_response:
            return await self.request(
                route, InteractionCallbackResponse, body=body, query={"with_response": True}, files=named
            )
        await self.request_empty(route, body=body, files=named)
        return None

    async def get_original_interaction_response(self, application_id: int, interaction_token: str) -> Message:
        """Get the message an interaction response created.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#get-original-interaction-response
        """
        return await self.request(
            GET_ORIGINAL_INTERACTION_RESPONSE.compile(
                application_id=application_id, interaction_token=interaction_token
            ),
            Message,
        )

    async def edit_original_interaction_response(
        self,
        application_id: int,
        interaction_token: str,
        params: EditWebhookMessageParams,
        *,
        files: Sequence[File] = (),
    ) -> Message:
        """Edit the message an interaction response created, or fill in a deferred one.

        Files passed are added to the message.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#edit-original-interaction-response
        """
        body, named = with_attachments(params, files, edit=True)
        return await self.request(
            EDIT_ORIGINAL_INTERACTION_RESPONSE.compile(
                application_id=application_id, interaction_token=interaction_token
            ),
            Message,
            body=body,
            files=named,
        )

    async def delete_original_interaction_response(self, application_id: int, interaction_token: str) -> None:
        """Delete the message an interaction response created.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#delete-original-interaction-response
        """
        await self.request_empty(
            DELETE_ORIGINAL_INTERACTION_RESPONSE.compile(
                application_id=application_id, interaction_token=interaction_token
            )
        )

    async def create_followup_message(
        self,
        application_id: int,
        interaction_token: str,
        params: CreateFollowupMessageParams,
        *,
        files: Sequence[File] = (),
    ) -> Message:
        """Send another message for an interaction, for up to 15 minutes after it.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#create-followup-message
        """
        body, named = with_attachments(params, files)
        return await self.request(
            CREATE_FOLLOWUP_MESSAGE.compile(
                application_id=application_id, interaction_token=interaction_token
            ),
            Message,
            body=body,
            files=named,
        )

    async def get_followup_message(
        self, application_id: int, interaction_token: str, message_id: int
    ) -> Message:
        """Get a follow-up message.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#get-followup-message
        """
        return await self.request(
            GET_FOLLOWUP_MESSAGE.compile(
                application_id=application_id, interaction_token=interaction_token, message_id=message_id
            ),
            Message,
        )

    async def edit_followup_message(
        self,
        application_id: int,
        interaction_token: str,
        message_id: int,
        params: EditWebhookMessageParams,
        *,
        files: Sequence[File] = (),
    ) -> Message:
        """Edit a follow-up message; files passed are added to it.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#edit-followup-message
        """
        body, named = with_attachments(params, files, edit=True)
        return await self.request(
            EDIT_FOLLOWUP_MESSAGE.compile(
                application_id=application_id, interaction_token=interaction_token, message_id=message_id
            ),
            Message,
            body=body,
            files=named,
        )

    async def delete_followup_message(
        self, application_id: int, interaction_token: str, message_id: int
    ) -> None:
        """Delete a follow-up message.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#delete-followup-message
        """
        await self.request_empty(
            DELETE_FOLLOWUP_MESSAGE.compile(
                application_id=application_id, interaction_token=interaction_token, message_id=message_id
            )
        )


def _response_with_files(
    response: InteractionResponse, files: Sequence[File]
) -> tuple[InteractionResponse, dict[str, File]]:
    """Attach `files` to the message a response carries.

    An update keeps the message's existing attachments, so its files are only appended.

    Raises:
        TypeError: `files` were given with a response that carries no message.
    """
    if not files:
        return response, {}
    if not isinstance(response, MessageResponse | UpdateMessageResponse):
        msg = f"{type(response).__name__} carries no message to attach files to"
        raise TypeError(msg)
    message, named = with_attachments(response.data, files, edit=isinstance(response, UpdateMessageResponse))
    return msgspec.structs.replace(response, data=message), named
