from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    CreateTestEntitlementParams,
    EntitlementOwnerType,
    ListEntitlementsParams,
    ListSubscriptionsParams,
)
from tests.support.json_payloads import ENTITLEMENT, SUBSCRIPTION
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

SKU: dict[str, object] = {
    "id": "1088510058284990888",
    "type": 5,
    "application_id": "788708323867885999",
    "name": "Test Premium",
    "slug": "test-premium",
    "flags": 128,
}
ENTITLEMENTS = "/applications/1019370614521200640/entitlements"

CASES = [
    EndpointCase(
        name="skus",
        call=lambda client: client.skus.list(788708323867885999),
        method="GET",
        path="/applications/788708323867885999/skus",
        response=[SKU],
    ),
    EndpointCase(
        name="entitlements",
        call=lambda client: client.entitlements.list(
            1019370614521200640,
            ListEntitlementsParams(sku_ids=[Snowflake(1), Snowflake(2)], exclude_ended=True, limit=100),
        ),
        method="GET",
        path=f"{ENTITLEMENTS}?limit=100&exclude_ended=true&sku_ids=1%2C2",
        response=[ENTITLEMENT],
    ),
    EndpointCase(
        name="entitlements of a user",
        call=lambda client: client.entitlements.list(
            1019370614521200640,
            ListEntitlementsParams(user_id=Snowflake(771129655544643584), exclude_deleted=False),
        ),
        method="GET",
        path=f"{ENTITLEMENTS}?user_id=771129655544643584&exclude_deleted=false",
        response=[{**ENTITLEMENT, "starts_at": None, "ends_at": None}],
    ),
    EndpointCase(
        name="all entitlements",
        call=lambda client: client.entitlements.list(1019370614521200640),
        method="GET",
        path=ENTITLEMENTS,
        response=[],
    ),
    EndpointCase(
        name="entitlement",
        call=lambda client: client.entitlements.get(1019370614521200640, 1019653849998299136),
        method="GET",
        path=f"{ENTITLEMENTS}/1019653849998299136",
        response=ENTITLEMENT,
    ),
    EndpointCase(
        name="consume",
        call=lambda client: client.entitlements.consume(1019370614521200640, 1019653849998299136),
        method="POST",
        path=f"{ENTITLEMENTS}/1019653849998299136/consume",
    ),
    EndpointCase(
        name="create test entitlement",
        call=lambda client: client.entitlements.create_test(
            1019370614521200640,
            CreateTestEntitlementParams(
                sku_id=Snowflake(999184799365857331),
                owner_id=Snowflake(847184799365857999),
                owner_type=EntitlementOwnerType.GUILD,
            ),
        ),
        method="POST",
        path=ENTITLEMENTS,
        body={"sku_id": "999184799365857331", "owner_id": "847184799365857999", "owner_type": 1},
        response={key: value for key, value in ENTITLEMENT.items() if key not in {"starts_at", "ends_at"}},
    ),
    EndpointCase(
        name="delete test entitlement",
        call=lambda client: client.entitlements.delete_test(1019370614521200640, 1019653849998299136),
        method="DELETE",
        path=f"{ENTITLEMENTS}/1019653849998299136",
    ),
    EndpointCase(
        name="subscriptions",
        call=lambda client: client.subscriptions.list(
            1158857122189168803, ListSubscriptionsParams(user_id=Snowflake(1088605110638227537))
        ),
        method="GET",
        path="/skus/1158857122189168803/subscriptions?user_id=1088605110638227537",
        response=[SUBSCRIPTION],
    ),
    EndpointCase(
        name="subscription",
        call=lambda client: client.subscriptions.get(1158857122189168803, 1278078770116427839),
        method="GET",
        path="/skus/1158857122189168803/subscriptions/1278078770116427839",
        response=SUBSCRIPTION,
    ),
]


@endpoint_cases(CASES)
async def test_monetization_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
