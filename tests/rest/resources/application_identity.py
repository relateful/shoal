from shoal.payloads import (
    DynamicMediaField,
    DynamicNumberField,
    Media,
    PrimaryProfileData,
    ProfileData,
    UpdateApplicationIdentityProfileParams,
)
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

PROFILE: dict[str, object] = {
    "username": "johndoe123",
    "metadata": None,
    "data": {
        "primary": {
            "season": "Season 3",
            "rank_name": "Silver",
            "rank_image": {"url": "https://example.com/assets/rank-images/silver.png"},
            "playtime_hours": 69.41,
            "total_wins": 57,
        },
        "dynamic": [
            {"type": 1, "name": "my_string", "value": "hello"},
            {"type": 2, "name": "my_number", "value": 123.45},
            {"type": 3, "name": "my_media", "value": {"url": "https://example.com/some-media.png"}},
        ],
    },
}
"""Discord's example, with fewer primary stats."""
IDENTITY: dict[str, object] = {
    "user_id": "1410709695433281536",
    "provider_type": "NONE",
    "provider_issued_user_id": "123456789123456789",
}
PROFILE_PATH = (
    "/applications/1410709600545542144/users/1410709695433281536/identities/123456789123456789/profile"
)

CASES = [
    EndpointCase(
        name="first profile write",
        call=lambda client: client.update_application_identity_profile(
            1410709600545542144,
            1410709695433281536,
            "123456789123456789",
            UpdateApplicationIdentityProfileParams(
                username="johndoe123",
                data=ProfileData(
                    primary=PrimaryProfileData(rank_name="Silver", playtime_hours=69.41),
                    dynamic=[
                        DynamicNumberField(name="my_number", value=123.45),
                        DynamicMediaField(name="my_media", value=Media(url="https://example.com/m.png")),
                    ],
                ),
            ),
        ),
        method="PATCH",
        path=PROFILE_PATH,
        body={
            "username": "johndoe123",
            "data": {
                "primary": {"rank_name": "Silver", "playtime_hours": 69.41},
                "dynamic": [
                    {"type": 2, "name": "my_number", "value": 123.45},
                    {"type": 3, "name": "my_media", "value": {"url": "https://example.com/m.png"}},
                ],
            },
        },
        response=PROFILE,
    ),
    EndpointCase(
        name="later profile write",
        call=lambda client: client.update_application_identity_profile(
            1410709600545542144,
            1410709695433281536,
            "123456789123456789",
            UpdateApplicationIdentityProfileParams(),
        ),
        method="PATCH",
        path=PROFILE_PATH,
        body={},
    ),
    EndpointCase(
        name="get profile",
        call=lambda client: client.get_application_identity_profile(
            1410709600545542144, 1410709695433281536, "123456789123456789"
        ),
        method="GET",
        path=PROFILE_PATH,
        response=PROFILE,
    ),
    EndpointCase(
        name="identities by user",
        call=lambda client: client.get_application_identities_by_user_id(
            1410709695433281536, 1410709600545542144
        ),
        method="GET",
        path="/users/1410709695433281536/application-identities/1410709600545542144",
        response={"identities": [IDENTITY]},
        result=[IDENTITY],
    ),
    EndpointCase(
        name="identities by external id",
        call=lambda client: client.get_application_identities_by_external_id(
            1410709600545542144, "steam", "765611", provider_id="eu"
        ),
        method="GET",
        path="/applications/1410709600545542144/application-identities/steam/765611?provider_id=eu",
        response={"identities": []},
        result=[],
    ),
    EndpointCase(
        name="delete identity",
        call=lambda client: client.delete_application_identity(
            1410709695433281536, 1410709600545542144, "NONE", "123"
        ),
        method="POST",
        path="/users/1410709695433281536/application-identities/1410709600545542144/NONE/123/delete",
    ),
]


@endpoint_cases(CASES)
async def test_application_identity_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
