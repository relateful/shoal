from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    CreateTestEntitlementParams,
    EntitlementOwnerType,
    ListEntitlementsParams,
    ListSKUSubscriptionsParams,
)
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

ENTITLEMENT: dict[str, object] = {
    "id": "1019653849998299136",
    "sku_id": "1019475255913222144",
    "application_id": "1019370614521200640",
    "user_id": "771129655544643584",
    "type": 8,
    "deleted": False,
    "starts_at": "2022-09-14T17:00:18.704163+00:00",
    "ends_at": "2022-10-14T17:00:18.704163+00:00",
    "guild_id": "1015034326372454400",
    "consumed": False,
}
"""Discord's example, in the field table's order and without the fields the table leaves out."""
SKU: dict[str, object] = {
    "id": "1088510058284990888",
    "type": 5,
    "application_id": "788708323867885999",
    "name": "Test Premium",
    "slug": "test-premium",
    "flags": 128,
}
SUBSCRIPTION: dict[str, object] = {
    "id": "1278078770116427839",
    "user_id": "1088605110638227537",
    "sku_ids": ["1158857122189168803"],
    "entitlement_ids": [],
    "renewal_sku_ids": None,
    "current_period_start": "2024-08-27T19:48:44.406602+00:00",
    "current_period_end": "2024-09-27T19:48:44.406602+00:00",
    "status": 0,
    "canceled_at": None,
}
"""Discord's example."""
ENTITLEMENTS = "/applications/1019370614521200640/entitlements"

CASES = [
    EndpointCase(
        name="skus",
        call=lambda client: client.list_skus(788708323867885999),
        method="GET",
        path="/applications/788708323867885999/skus",
        response=[SKU],
    ),
    EndpointCase(
        name="entitlements",
        call=lambda client: client.list_entitlements(
            1019370614521200640,
            ListEntitlementsParams(sku_ids=[Snowflake(1), Snowflake(2)], exclude_ended=True, limit=100),
        ),
        method="GET",
        path=f"{ENTITLEMENTS}?limit=100&exclude_ended=true&sku_ids=1%2C2",
        response=[ENTITLEMENT],
    ),
    EndpointCase(
        name="entitlement",
        call=lambda client: client.get_entitlement(1019370614521200640, 1019653849998299136),
        method="GET",
        path=f"{ENTITLEMENTS}/1019653849998299136",
        response=ENTITLEMENT,
    ),
    EndpointCase(
        name="consume",
        call=lambda client: client.consume_an_entitlement(1019370614521200640, 1019653849998299136),
        method="POST",
        path=f"{ENTITLEMENTS}/1019653849998299136/consume",
    ),
    EndpointCase(
        name="create test entitlement",
        call=lambda client: client.create_test_entitlement(
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
        call=lambda client: client.delete_test_entitlement(1019370614521200640, 1019653849998299136),
        method="DELETE",
        path=f"{ENTITLEMENTS}/1019653849998299136",
    ),
    EndpointCase(
        name="subscriptions",
        call=lambda client: client.list_sku_subscriptions(
            1158857122189168803, ListSKUSubscriptionsParams(user_id=Snowflake(1088605110638227537))
        ),
        method="GET",
        path="/skus/1158857122189168803/subscriptions?user_id=1088605110638227537",
        response=[SUBSCRIPTION],
    ),
    EndpointCase(
        name="subscription",
        call=lambda client: client.get_sku_subscription(1158857122189168803, 1278078770116427839),
        method="GET",
        path="/skus/1158857122189168803/subscriptions/1278078770116427839",
        response=SUBSCRIPTION,
    ),
]


@endpoint_cases(CASES)
async def test_monetization_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
