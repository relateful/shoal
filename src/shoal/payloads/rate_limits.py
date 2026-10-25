"""HTTP rate limits: the documented limits and the 429 response.

Discord: https://docs.discord.com/developers/topics/rate-limits
"""

from http import HTTPStatus
from typing import Final

from msgspec import UNSET, UnsetType, field

from shoal.core.enums import DiscordStrEnum
from shoal.payloads.base import Payload
from shoal.payloads.errors import JSONErrorCode

GLOBAL_REQUESTS_PER_SECOND: Final = 50
"""Requests per second a bot may make across all routes, unless Discord raised its limit.

Discord: https://docs.discord.com/developers/topics/rate-limits#global-rate-limit
"""

INVALID_REQUEST_LIMIT: Final = 10_000
"""Invalid responses tolerated per window before Cloudflare bans the IP.

Discord: https://docs.discord.com/developers/topics/rate-limits#invalid-request-limit-aka-cloudflare-bans
"""

INVALID_REQUEST_STATUSES: Final = frozenset(
    {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN, HTTPStatus.TOO_MANY_REQUESTS}
)
"""Statuses that count as invalid requests (except 429s with scope `shared`).

Discord: https://docs.discord.com/developers/topics/rate-limits#invalid-request-limit-aka-cloudflare-bans
"""

INVALID_REQUEST_WINDOW: Final = 600.0
"""The invalid request window, in seconds.

Discord: https://docs.discord.com/developers/topics/rate-limits#invalid-request-limit-aka-cloudflare-bans
"""

MAJOR_PARAMETERS: Final = frozenset(
    {"channel_id", "guild_id", "webhook_id", "webhook_token", "interaction_id", "interaction_token"}
)
"""Path parameters that are top-level resources: each value gets its own rate limit bucket.

Discord: https://docs.discord.com/developers/topics/rate-limits
"""


class RateLimitScope(DiscordStrEnum):
    """The `X-RateLimit-Scope` header on a 429.

    `shared` limits are per-resource and do not count towards the invalid request limit.

    Discord: https://docs.discord.com/developers/topics/rate-limits#header-format
    """

    GLOBAL = "global"
    SHARED = "shared"
    USER = "user"


class RateLimitResponse(Payload):
    """The JSON body of a 429 response.

    Discord: https://docs.discord.com/developers/topics/rate-limits#exceeding-a-rate-limit-rate-limit-response-structure
    """

    message: str
    retry_after: float
    global_: bool = field(default=False, name="global")
    code: JSONErrorCode | UnsetType = UNSET
