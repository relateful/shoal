"""Monetization: SKUs, entitlements and subscriptions.

Discord: https://docs.discord.com/developers/monetization/overview
"""

from datetime import datetime

from msgspec import UNSET, UnsetType

from shoal.core.enums import DiscordIntEnum
from shoal.core.flags import BaseFlags, flag
from shoal.core.snowflake import Snowflake
from shoal.payloads.base import Payload


class SKUType(DiscordIntEnum):
    """What an SKU sells.

    Discord: https://docs.discord.com/developers/resources/sku#sku-object-sku-types
    """

    DURABLE = 2
    """A one-time purchase that is kept."""
    CONSUMABLE = 3
    """A one-time purchase that can be used up."""
    SUBSCRIPTION = 5
    SUBSCRIPTION_GROUP = 6
    """Created by Discord for each subscription SKU; not used directly."""


class SKUFlags(BaseFlags):
    """Flags of an SKU.

    Discord: https://docs.discord.com/developers/resources/sku#sku-object-sku-flags
    """

    __slots__ = ()

    available = flag(2)
    guild_subscription = flag(7)
    """Bought by a user for one guild; everyone in it gets the benefits."""
    user_subscription = flag(8)
    """Bought by a user for themselves, in every guild."""


class SKU(Payload):
    """Something an app sells.

    Discord: https://docs.discord.com/developers/resources/sku#sku-object
    """

    id: Snowflake
    type: SKUType
    application_id: Snowflake
    name: str
    slug: str
    flags: SKUFlags


class EntitlementType(DiscordIntEnum):
    """How a user or guild got an entitlement.

    Discord: https://docs.discord.com/developers/resources/entitlement#entitlement-object-entitlement-types
    """

    PURCHASE = 1
    PREMIUM_SUBSCRIPTION = 2
    DEVELOPER_GIFT = 3
    TEST_MODE_PURCHASE = 4
    FREE_PURCHASE = 5
    USER_GIFT = 6
    PREMIUM_PURCHASE = 7
    """Claimed for free by a Nitro subscriber."""
    APPLICATION_SUBSCRIPTION = 8


class Entitlement(Payload):
    """A user's or guild's access to an SKU.

    Discord: https://docs.discord.com/developers/resources/entitlement#entitlement-object
    """

    id: Snowflake
    sku_id: Snowflake
    application_id: Snowflake
    user_id: Snowflake | UnsetType = UNSET
    type: EntitlementType
    deleted: bool
    starts_at: datetime | UnsetType | None = UNSET
    """Discord's table lists it as always present; Create Test Entitlement leaves it out."""
    ends_at: datetime | UnsetType | None = UNSET
    """Discord's table lists it as always present; Create Test Entitlement leaves it out."""
    guild_id: Snowflake | UnsetType = UNSET
    consumed: bool | UnsetType = UNSET
    """For consumable SKUs."""


class ListEntitlementsParams(Payload):
    """Query of List Entitlements.

    Discord: https://docs.discord.com/developers/resources/entitlement#list-entitlements-query-string-params
    """

    user_id: Snowflake | UnsetType = UNSET
    sku_ids: list[Snowflake] | UnsetType = UNSET
    """Sent comma-separated."""
    before: Snowflake | UnsetType = UNSET
    after: Snowflake | UnsetType = UNSET
    limit: int | UnsetType = UNSET
    """1 to 100, Discord's default."""
    guild_id: Snowflake | UnsetType = UNSET
    exclude_ended: bool | UnsetType = UNSET
    """Discord's default is `False`."""
    exclude_deleted: bool | UnsetType = UNSET
    """Discord's default is `True`."""


class EntitlementOwnerType(DiscordIntEnum):
    """Who a test entitlement is for.

    Discord: https://docs.discord.com/developers/resources/entitlement#create-test-entitlement-json-params
    """

    GUILD = 1
    USER = 2


class CreateTestEntitlementParams(Payload):
    """JSON body of Create Test Entitlement.

    Discord: https://docs.discord.com/developers/resources/entitlement#create-test-entitlement-json-params
    """

    sku_id: Snowflake
    owner_id: Snowflake
    """The guild or user."""
    owner_type: EntitlementOwnerType


class SubscriptionStatus(DiscordIntEnum):
    """Whether a subscription renews. Grant access by entitlements, not by this.

    Discord: https://docs.discord.com/developers/resources/subscription#subscription-statuses
    """

    ACTIVE = 0
    INACTIVE = 1
    ENDING = 2
    """Active, but will not renew."""


class Subscription(Payload):
    """A user's subscription to an app's SKUs.

    Discord: https://docs.discord.com/developers/resources/subscription#subscription-object
    """

    id: Snowflake
    user_id: Snowflake
    sku_ids: list[Snowflake]
    entitlement_ids: list[Snowflake]
    renewal_sku_ids: list[Snowflake] | None
    current_period_start: datetime
    current_period_end: datetime
    status: SubscriptionStatus
    canceled_at: datetime | None
    country: str | UnsetType = UNSET
    """ISO 3166-1 alpha-2 code; only with a private OAuth2 scope."""


class ListSKUSubscriptionsParams(Payload):
    """Query of List SKU Subscriptions.

    Discord: https://docs.discord.com/developers/resources/subscription#list-sku-subscriptions
    """

    before: Snowflake | UnsetType = UNSET
    after: Snowflake | UnsetType = UNSET
    limit: int | UnsetType = UNSET
    """1 to 100; Discord's default is 50."""
    user_id: Snowflake | UnsetType = UNSET
    """Required, except with an OAuth2 token."""
