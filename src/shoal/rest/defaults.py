"""Shoal's own REST defaults: tunables and choices that are not Discord facts.

Discord-documented rate limit constants live in `shoal.payloads.rate_limits`. Nothing here is defined
anywhere else.
"""

from http import HTTPStatus
from typing import Final

from shoal._version import __version__
from shoal.payloads.api import USER_AGENT_FORMAT

BUCKET_PRUNE_INTERVAL: Final = 60.0
"""Seconds between scans for idle rate limit buckets, once there are enough to prune."""

BUCKET_PRUNE_THRESHOLD: Final = 1024
"""Rate limit buckets kept before idle ones are pruned."""

DEFAULT_USER_AGENT: Final = USER_AGENT_FORMAT.format(
    url="https://github.com/shoal-py/shoal", version=__version__
)
"""The `User-Agent` Shoal sends, in the shape Discord requires.

Discord: https://docs.discord.com/developers/reference#user-agent
"""

INVALID_REQUEST_SAFETY_MARGIN: Final = 500
"""How far below Discord's invalid request limit the guard starts holding requests back."""

MAX_RATE_LIMIT_WAIT: Final = 60.0
"""The longest 429 wait, in seconds, a request sits through before `RateLimitedError` is raised."""

MAX_RETRIES: Final = 3
"""Retries for rate limits, idempotent requests that hit a 5xx, and network errors."""

PROXY_HOST: Final = "127.0.0.1"
"""The address `RestProxy` listens on: this machine only, until it is told otherwise."""

PROXY_MAX_BODY_SIZE: Final = 512 * 1024 * 1024
"""The largest request body `RestProxy` accepts, in bytes. Shoal's own bound: Discord's limit applies
per file, rises with a guild's boost tier, and a message carries several files.

Discord: https://docs.discord.com/developers/reference#uploading-files
"""

PROXY_PATH: Final = "/api"
"""The path `RestProxy` serves under; clients use `http://host:port/api` as their `base_url`."""

PROXY_PORT: Final = 8080
"""The port `RestProxy` listens on."""

PROXY_SECRET_HEADER: Final = "X-Shoal-Proxy-Secret"  # noqa: S105 - a header name, not a secret
"""The header that carries the proxy's secret from `RestClient(proxy_secret=...)` to `RestProxy`."""

REQUEST_TIMEOUT: Final = 30.0
"""Seconds allowed per HTTP request, including reading the body."""

RETRYABLE_STATUSES: Final = frozenset(
    {
        HTTPStatus.INTERNAL_SERVER_ERROR,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
        524,
    }
)
"""5xx statuses worth retrying for idempotent requests. 524 is Cloudflare's origin timeout."""

RETRY_BACKOFF_CAP: Final = 30.0
"""The longest backoff, in seconds, between retries of a failed request."""

SEARCH_INDEX_RETRY_DELAY: Final = 1.0
"""Seconds to wait before retrying a search when Discord says the index is not ready and gives
no `retry_after`. Discord asks for "a short delay" in that case."""
