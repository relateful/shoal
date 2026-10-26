"""Endpoints for application identity profiles: game stats on players' Discord profiles.

All need a bot token, and the player must have authorized the app with the
`application_identities.write` scope.

Discord: https://docs.discord.com/developers/resources/application-identity-profile
"""

from shoal.payloads.application_identity import (
    ApplicationIdentities,
    ApplicationIdentity,
    ApplicationIdentityProfile,
    DeleteIdentityParams,
    EditIdentityProfileParams,
)
from shoal.rest.endpoints import (
    DELETE_APPLICATION_IDENTITY,
    GET_APPLICATION_IDENTITIES_BY_EXTERNAL_ID,
    GET_APPLICATION_IDENTITIES_BY_USER_ID,
    GET_APPLICATION_IDENTITY_PROFILE,
    UPDATE_APPLICATION_IDENTITY_PROFILE,
)
from shoal.rest.requester import Resource


class Identities(Resource):
    """Application identities and their profiles.

    Use it as `rest.identities`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def edit_profile(
        self,
        application_id: int,
        user_id: int,
        provider_issued_user_id: str,
        params: EditIdentityProfileParams,
    ) -> ApplicationIdentityProfile | None:
        """Store a player's stats; `data`, when given, replaces all of them.

        Returns the profile when this first write created it, and `None` for later updates.

        Discord: https://docs.discord.com/developers/resources/application-identity-profile#update-application-identity-profile
        """
        return await self.request_optional(
            UPDATE_APPLICATION_IDENTITY_PROFILE.compile(
                application_id=application_id,
                user_id=user_id,
                provider_issued_user_id=provider_issued_user_id,
            ),
            ApplicationIdentityProfile,
            body=params,
        )

    async def get_profile(
        self, application_id: int, user_id: int, provider_issued_user_id: str
    ) -> ApplicationIdentityProfile:
        """Get the stats stored for a player.

        Discord: https://docs.discord.com/developers/resources/application-identity-profile#get-application-identity-profile
        """
        return await self.request(
            GET_APPLICATION_IDENTITY_PROFILE.compile(
                application_id=application_id,
                user_id=user_id,
                provider_issued_user_id=provider_issued_user_id,
            ),
            ApplicationIdentityProfile,
        )

    async def list_by_user(self, user_id: int, application_id: int) -> list[ApplicationIdentity]:
        """List a Discord user's identities in the app.

        Discord: https://docs.discord.com/developers/resources/application-identity-profile#get-application-identities-by-user-id
        """
        response = await self.request(
            GET_APPLICATION_IDENTITIES_BY_USER_ID.compile(user_id=user_id, application_id=application_id),
            ApplicationIdentities,
        )
        return response.identities

    async def list_by_external_id(
        self,
        application_id: int,
        provider_type: str,
        provider_issued_user_id: str,
        *,
        provider_id: str | None = None,
    ) -> list[ApplicationIdentity]:
        """Find the Discord user behind a game account; empty when none matches.

        Discord: https://docs.discord.com/developers/resources/application-identity-profile#get-application-identities-by-external-id
        """
        response = await self.request(
            GET_APPLICATION_IDENTITIES_BY_EXTERNAL_ID.compile(
                application_id=application_id,
                provider_type=provider_type,
                provider_issued_user_id=provider_issued_user_id,
            ),
            ApplicationIdentities,
            query={"provider_id": provider_id} if provider_id is not None else None,
        )
        return response.identities

    async def delete(
        self,
        user_id: int,
        application_id: int,
        provider_type: str,
        provider_issued_user_id: str,
        *,
        provider_id: str | None = None,
    ) -> None:
        """Delete one identity and its stats; refused for the user's last account-linking identity.

        Discord: https://docs.discord.com/developers/resources/application-identity-profile#delete-application-identity
        """
        await self.request_empty(
            DELETE_APPLICATION_IDENTITY.compile(
                user_id=user_id,
                application_id=application_id,
                provider_type=provider_type,
                provider_issued_user_id=provider_issued_user_id,
            ),
            body=DeleteIdentityParams(provider_id=provider_id) if provider_id is not None else None,
        )
