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
from tests.support.json_payloads import USER
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

APPLICATION: dict[str, object] = {
    "id": "172150183260323840",
    "name": "Baba O-Riley",
    "icon": None,
    "description": "Test",
    "bot_public": True,
    "bot_require_code_grant": False,
    "owner": USER,
    "verify_key": "1e0a356058d627ca38a5c8c9648818061d49e49bd9da9e3ab17d98ad4d6bg2u8",
    "team": {
        "icon": "dd9b7dcfdf5351b9c3de0fe167bacbe1",
        "id": "531992624043786253",
        "members": [{"membership_state": 2, "team_id": "531992624043786253", "user": USER, "role": "admin"}],
        "name": "A team",
        "owner_user_id": "511972282709709995",
    },
    "guild_id": "290926798626357260",
    "primary_sku_id": "172150183260323840",
    "slug": "test",
    "cover_image": "31deabb7e45b6c8ecfef77d2f99c81a5",
    "flags": 8192,
    "flags_new": "8192",
    "interactions_endpoint_url": None,
    "role_connections_verification_url": None,
    "event_webhooks_url": None,
    "event_webhooks_status": 1,
    "integration_types_config": {
        "0": {"oauth2_install_params": {"scopes": ["applications.commands", "bot"], "permissions": "2048"}},
        "1": {"oauth2_install_params": {"scopes": ["applications.commands"], "permissions": "0"}},
    },
}
"""Discord's example, in the field table's order and with the team member's `role`."""
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
