from shoal.payloads import (
    ApplicationFlags,
    ApplicationIntegrationType,
    ApplicationIntegrationTypeConfiguration,
    ApplicationRoleConnectionMetadata,
    ApplicationRoleConnectionMetadataType,
    EditCurrentApplicationParams,
    InstallParams,
    Permissions,
)
from tests.support.json_payloads import APPLICATION, USER
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

METADATA: dict[str, object] = {
    "type": 2,
    "key": "level",
    "name": "Level",
    "name_localizations": {"fr": "Niveau"},
    "description": "Your level in the game",
}

CASES = [
    EndpointCase(
        name="get current application",
        call=lambda client: client.applications.get_me(),
        method="GET",
        path="/applications/@me",
        response=APPLICATION,
    ),
    EndpointCase(
        name="edit current application",
        call=lambda client: client.applications.edit_me(
            EditCurrentApplicationParams(
                flags=ApplicationFlags(gateway_message_content_limited=True),
                icon=None,
                integration_types_config={
                    ApplicationIntegrationType.GUILD_INSTALL: ApplicationIntegrationTypeConfiguration(
                        oauth2_install_params=InstallParams(
                            scopes=["bot"], permissions=Permissions(send_messages=True)
                        )
                    )
                },
            )
        ),
        method="PATCH",
        path="/applications/@me",
        body={
            "integration_types_config": {
                "0": {"oauth2_install_params": {"scopes": ["bot"], "permissions": "2048"}}
            },
            "flags": 524288,
            "icon": None,
        },
        response=APPLICATION,
    ),
    EndpointCase(
        name="activity instance",
        call=lambda client: client.applications.get_activity_instance(
            1215413995645968394, "i-1276580072400224306"
        ),
        method="GET",
        path="/applications/1215413995645968394/activity-instances/i-1276580072400224306",
        response={
            "application_id": "1215413995645968394",
            "instance_id": "i-1276580072400224306",
            "launch_id": "1276580072400224306",
            "location": {
                "id": "gc-912952092627435520-912954213460484116",
                "kind": "gc",
                "channel_id": "912954213460484116",
                "guild_id": "912952092627435520",
            },
            "users": ["205519959982473217"],
        },
    ),
    EndpointCase(
        name="role connection metadata",
        call=lambda client: client.role_connections.list_metadata(7),
        method="GET",
        path="/applications/7/role-connections/metadata",
        response=[METADATA],
    ),
    EndpointCase(
        name="update role connection metadata",
        call=lambda client: client.role_connections.overwrite_metadata(
            7,
            [
                ApplicationRoleConnectionMetadata(
                    type=ApplicationRoleConnectionMetadataType.BOOLEAN_EQUAL,
                    key="verified",
                    name="Verified",
                    description="Has verified their account",
                )
            ],
        ),
        method="PUT",
        path="/applications/7/role-connections/metadata",
        body=[
            {"type": 7, "key": "verified", "name": "Verified", "description": "Has verified their account"}
        ],
        response=[METADATA],
    ),
    EndpointCase(
        name="bot application information",
        call=lambda client: client.oauth2.get_application(),
        method="GET",
        path="/oauth2/applications/@me",
        response=APPLICATION,
    ),
    EndpointCase(
        name="authorization information",
        call=lambda client: client.oauth2.get_authorization(),
        method="GET",
        path="/oauth2/@me",
        response={
            "application": {
                "id": "159799960412356608",
                "name": "AIRHORN SOLUTIONS",
                "icon": "f03590d3eb764081d154a66340ea7d6d",
                "description": "",
                "bot_public": True,
                "bot_require_code_grant": False,
                "verify_key": "c8cde6a3c8c6e49d86af3191287b3ce255872be1fff6dc285bdb420c06a2c3c8",
            },
            "scopes": ["guilds.join", "identify"],
            "expires": "2021-01-23T02:33:17.017000+00:00",
            "user": USER,
        },
    ),
]


@endpoint_cases(CASES)
async def test_application_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
