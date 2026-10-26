"""Endpoints for the app itself.

Its settings, Activity instances, linked-role metadata, and the OAuth2 information endpoints.

Discord: https://docs.discord.com/developers/resources/application
"""

from collections.abc import Sequence

from shoal.payloads.application import (
    ActivityInstance,
    Application,
    ApplicationRoleConnectionMetadata,
    AuthorizationInformation,
    EditCurrentApplicationParams,
)
from shoal.rest.endpoints import (
    EDIT_CURRENT_APPLICATION,
    GET_APPLICATION_ACTIVITY_INSTANCE,
    GET_APPLICATION_ROLE_CONNECTION_METADATA_RECORDS,
    GET_CURRENT_APPLICATION,
    GET_CURRENT_AUTHORIZATION_INFORMATION,
    GET_CURRENT_BOT_APPLICATION_INFORMATION,
    UPDATE_APPLICATION_ROLE_CONNECTION_METADATA_RECORDS,
)
from shoal.rest.requester import Requester


class ApplicationEndpoints(Requester):
    """Endpoints for the app itself; part of `RestClient`."""

    __slots__ = ()

    async def get_current_application(self) -> Application:
        """Get the bot's app.

        Discord: https://docs.discord.com/developers/resources/application#get-current-application
        """
        return await self.request(GET_CURRENT_APPLICATION.compile(), Application)

    async def edit_current_application(self, params: EditCurrentApplicationParams) -> Application:
        """Change the bot's app; only the fields given change.

        Discord: https://docs.discord.com/developers/resources/application#edit-current-application
        """
        return await self.request(EDIT_CURRENT_APPLICATION.compile(), Application, body=params)

    async def get_application_activity_instance(
        self, application_id: int, instance_id: str
    ) -> ActivityInstance:
        """Get a running Activity instance, to check who is really in it.

        Discord: https://docs.discord.com/developers/resources/application#get-application-activity-instance
        """
        return await self.request(
            GET_APPLICATION_ACTIVITY_INSTANCE.compile(application_id=application_id, instance_id=instance_id),
            ActivityInstance,
        )

    async def get_application_role_connection_metadata_records(
        self, application_id: int
    ) -> list[ApplicationRoleConnectionMetadata]:
        """List the values the app records for linked roles.

        Discord: https://docs.discord.com/developers/resources/application-role-connection-metadata#get-application-role-connection-metadata-records
        """
        return await self.request(
            GET_APPLICATION_ROLE_CONNECTION_METADATA_RECORDS.compile(application_id=application_id),
            list[ApplicationRoleConnectionMetadata],
        )

    async def update_application_role_connection_metadata_records(
        self, application_id: int, records: Sequence[ApplicationRoleConnectionMetadata]
    ) -> list[ApplicationRoleConnectionMetadata]:
        """Replace the values the app records for linked roles; at most 5.

        Discord: https://docs.discord.com/developers/resources/application-role-connection-metadata#update-application-role-connection-metadata-records
        """
        return await self.request(
            UPDATE_APPLICATION_ROLE_CONNECTION_METADATA_RECORDS.compile(application_id=application_id),
            list[ApplicationRoleConnectionMetadata],
            body=list(records),
        )

    async def get_current_bot_application_information(self) -> Application:
        """Get the bot's app through the OAuth2 endpoint.

        Discord: https://docs.discord.com/developers/topics/oauth2#get-current-bot-application-information
        """
        return await self.request(GET_CURRENT_BOT_APPLICATION_INFORMATION.compile(), Application)

    async def get_current_authorization_information(self) -> AuthorizationInformation:
        """Get what the bearer token was authorized for. Needs a bearer token.

        Discord: https://docs.discord.com/developers/topics/oauth2#get-current-authorization-information
        """
        return await self.request(GET_CURRENT_AUTHORIZATION_INFORMATION.compile(), AuthorizationInformation)
