"""Endpoints for SKUs, entitlements and subscriptions.

Discord: https://docs.discord.com/developers/monetization/overview
"""

from shoal.payloads.monetization import (
    SKU,
    CreateTestEntitlementParams,
    Entitlement,
    ListEntitlementsParams,
    ListSKUSubscriptionsParams,
    Subscription,
)
from shoal.rest.endpoints import (
    CONSUME_AN_ENTITLEMENT,
    CREATE_TEST_ENTITLEMENT,
    DELETE_TEST_ENTITLEMENT,
    GET_ENTITLEMENT,
    GET_SKU_SUBSCRIPTION,
    LIST_ENTITLEMENTS,
    LIST_SKU_SUBSCRIPTIONS,
    LIST_SKUS,
)
from shoal.rest.requester import Requester, comma_joined, query_of


class MonetizationEndpoints(Requester):
    """Endpoints for SKUs, entitlements and subscriptions; part of `RestClient`."""

    __slots__ = ()

    async def list_skus(self, application_id: int) -> list[SKU]:
        """List the app's SKUs. A subscription appears twice: use the one of type `SUBSCRIPTION`.

        Discord: https://docs.discord.com/developers/resources/sku#list-skus
        """
        return await self.request(LIST_SKUS.compile(application_id=application_id), list[SKU])

    async def list_entitlements(
        self, application_id: int, params: ListEntitlementsParams | None = None
    ) -> list[Entitlement]:
        """List the app's entitlements, active and ended, up to 100 at a time.

        Discord: https://docs.discord.com/developers/resources/entitlement#list-entitlements
        """
        query = comma_joined(query_of(params), "sku_ids") if params is not None else {}
        return await self.request(
            LIST_ENTITLEMENTS.compile(application_id=application_id), list[Entitlement], query=query or None
        )

    async def get_entitlement(self, application_id: int, entitlement_id: int) -> Entitlement:
        """Get one entitlement.

        Discord: https://docs.discord.com/developers/resources/entitlement#get-entitlement
        """
        return await self.request(
            GET_ENTITLEMENT.compile(application_id=application_id, entitlement_id=entitlement_id), Entitlement
        )

    async def consume_an_entitlement(self, application_id: int, entitlement_id: int) -> None:
        """Mark a consumable one-time purchase as used.

        Discord: https://docs.discord.com/developers/resources/entitlement#consume-an-entitlement
        """
        await self.request_empty(
            CONSUME_AN_ENTITLEMENT.compile(application_id=application_id, entitlement_id=entitlement_id)
        )

    async def create_test_entitlement(
        self, application_id: int, params: CreateTestEntitlementParams
    ) -> Entitlement:
        """Give a user or guild an SKU for testing, with no end date.

        Discord: https://docs.discord.com/developers/resources/entitlement#create-test-entitlement
        """
        return await self.request(
            CREATE_TEST_ENTITLEMENT.compile(application_id=application_id), Entitlement, body=params
        )

    async def delete_test_entitlement(self, application_id: int, entitlement_id: int) -> None:
        """Remove a test entitlement.

        Discord: https://docs.discord.com/developers/resources/entitlement#delete-test-entitlement
        """
        await self.request_empty(
            DELETE_TEST_ENTITLEMENT.compile(application_id=application_id, entitlement_id=entitlement_id)
        )

    async def list_sku_subscriptions(
        self, sku_id: int, params: ListSKUSubscriptionsParams | None = None
    ) -> list[Subscription]:
        """List subscriptions to an SKU; with a bot token, `user_id` is required.

        Discord: https://docs.discord.com/developers/resources/subscription#list-sku-subscriptions
        """
        return await self.request(
            LIST_SKU_SUBSCRIPTIONS.compile(sku_id=sku_id),
            list[Subscription],
            query=query_of(params) if params is not None else None,
        )

    async def get_sku_subscription(self, sku_id: int, subscription_id: int) -> Subscription:
        """Get one subscription.

        Discord: https://docs.discord.com/developers/resources/subscription#get-sku-subscription
        """
        return await self.request(
            GET_SKU_SUBSCRIPTION.compile(sku_id=sku_id, subscription_id=subscription_id), Subscription
        )
