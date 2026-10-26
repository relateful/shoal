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
from shoal.payloads.user import (
    ApplicationRoleConnection,
    EditRoleConnectionParams,
)
from shoal.rest.endpoints import (
    DELETE_CURRENT_USER_APPLICATION_ROLE_CONNECTION,
    EDIT_CURRENT_APPLICATION,
    GET_APPLICATION_ACTIVITY_INSTANCE,
    GET_APPLICATION_ROLE_CONNECTION_METADATA_RECORDS,
    GET_CURRENT_APPLICATION,
    GET_CURRENT_AUTHORIZATION_INFORMATION,
    GET_CURRENT_BOT_APPLICATION_INFORMATION,
    GET_CURRENT_USER_APPLICATION_ROLE_CONNECTION,
    UPDATE_APPLICATION_ROLE_CONNECTION_METADATA_RECORDS,
    UPDATE_CURRENT_USER_APPLICATION_ROLE_CONNECTION,
)
from shoal.rest.requester import Resource


class Applications(Resource):
    """The bot's own application and its activity instances.

    Use it as `rest.applications`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def get_me(self) -> Application:
        """Get the bot's app.

        Discord: https://docs.discord.com/developers/resources/application#get-current-application
        """
        return await self.request(GET_CURRENT_APPLICATION.compile(), Application)

    async def edit_me(self, params: EditCurrentApplicationParams) -> Application:
        """Change the bot's app; only the fields given change.

        Discord: https://docs.discord.com/developers/resources/application#edit-current-application
        """
        return await self.request(EDIT_CURRENT_APPLICATION.compile(), Application, body=params)

    async def get_activity_instance(self, application_id: int, instance_id: str) -> ActivityInstance:
        """Get a running Activity instance, to check who is really in it.

        Discord: https://docs.discord.com/developers/resources/application#get-application-activity-instance
        """
        return await self.request(
            GET_APPLICATION_ACTIVITY_INSTANCE.compile(application_id=application_id, instance_id=instance_id),
            ActivityInstance,
        )


class OAuth2(Resource):
    """What the current OAuth2 token is for.

    Use it as `rest.oauth2`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def get_application(self) -> Application:
        """Get the bot's app through the OAuth2 endpoint.

        Discord: https://docs.discord.com/developers/topics/oauth2#get-current-bot-application-information
        """
        return await self.request(GET_CURRENT_BOT_APPLICATION_INFORMATION.compile(), Application)

    async def get_authorization(self) -> AuthorizationInformation:
        """Get what the bearer token was authorized for. Needs a bearer token.

        Discord: https://docs.discord.com/developers/topics/oauth2#get-current-authorization-information
        """
        return await self.request(GET_CURRENT_AUTHORIZATION_INFORMATION.compile(), AuthorizationInformation)


class RoleConnections(Resource):
    """Linked roles: the metadata records and a user's connection.

    Use it as `rest.role_connections`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def list_metadata(self, application_id: int) -> list[ApplicationRoleConnectionMetadata]:
        """List the values the app records for linked roles.

        Discord: https://docs.discord.com/developers/resources/application-role-connection-metadata#get-application-role-connection-metadata-records
        """
        return await self.request(
            GET_APPLICATION_ROLE_CONNECTION_METADATA_RECORDS.compile(application_id=application_id),
            list[ApplicationRoleConnectionMetadata],
        )

    async def overwrite_metadata(
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

    async def get_me(self, application_id: int) -> ApplicationRoleConnection:
        """Get what the app has recorded about the user for linked roles.

        Needs a bearer token with the `role_connections.write` scope for that app.

        Discord: https://docs.discord.com/developers/resources/user#get-current-user-application-role-connection
        """
        return await self.request(
            GET_CURRENT_USER_APPLICATION_ROLE_CONNECTION.compile(application_id=application_id),
            ApplicationRoleConnection,
        )

    async def edit_me(
        self, application_id: int, params: EditRoleConnectionParams
    ) -> ApplicationRoleConnection:
        """Record what linked roles check against for the user.

        Needs a bearer token with the `role_connections.write` scope for that app.

        Discord: https://docs.discord.com/developers/resources/user#update-current-user-application-role-connection
        """
        return await self.request(
            UPDATE_CURRENT_USER_APPLICATION_ROLE_CONNECTION.compile(application_id=application_id),
            ApplicationRoleConnection,
            body=params,
        )

    async def delete_me(self, application_id: int) -> None:
        """Remove what the app has recorded about the user for linked roles.

        Needs a bearer token with the `role_connections.write` scope for that app.

        Discord: https://docs.discord.com/developers/resources/user#delete-current-user-application-role-connection
        """
        await self.request_empty(
            DELETE_CURRENT_USER_APPLICATION_ROLE_CONNECTION.compile(application_id=application_id)
        )
