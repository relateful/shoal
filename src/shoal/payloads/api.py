"""API-wide constants: version, base URLs and the required user agent.

Discord: https://docs.discord.com/developers/reference
"""

from typing import Final

API_BASE_URL: Final = "https://discord.com/api"
"""Base URL of the HTTP API, without the version segment.

Discord: https://docs.discord.com/developers/reference
"""

API_VERSION: Final = 10
"""The HTTP and gateway API version Shoal speaks.

Discord: https://docs.discord.com/developers/reference#api-versioning
"""

AUDIT_LOG_REASON_MAX_LENGTH: Final = 512
"""The longest `X-Audit-Log-Reason` value, in characters, before URL encoding.

Discord: https://docs.discord.com/developers/resources/audit-log#audit-log-entry-object
"""

DOCS_BASE_URL: Final = "https://docs.discord.com/developers/"
"""Where Discord publishes its developer documentation; every docs link in Shoal starts with this."""

USER_AGENT_FORMAT: Final = "DiscordBot ({url}, {version})"
"""The `User-Agent` shape Discord requires on every HTTP request.

Discord: https://docs.discord.com/developers/reference#user-agent
"""
