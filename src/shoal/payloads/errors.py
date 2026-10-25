"""Error bodies and JSON error codes.

Discord: https://docs.discord.com/developers/topics/opcodes-and-status-codes#json
"""

from msgspec import UNSET, Raw, UnsetType

from shoal.core.enums import DiscordIntEnum
from shoal.payloads.base import Payload


class JSONErrorCode(DiscordIntEnum):
    """The `code` field of a Discord error response.

    Only the codes a library or bot commonly branches on are named; every other documented (or
    future) code still decodes as an `UNKNOWN_<code>` pseudo-member with its integer value intact.

    Discord: https://docs.discord.com/developers/topics/opcodes-and-status-codes#json-json-error-codes
    """

    GENERAL_ERROR = 0
    UNKNOWN_ACCOUNT = 10001
    UNKNOWN_APPLICATION = 10002
    UNKNOWN_CHANNEL = 10003
    UNKNOWN_GUILD = 10004
    UNKNOWN_INTEGRATION = 10005
    UNKNOWN_INVITE = 10006
    UNKNOWN_MEMBER = 10007
    UNKNOWN_MESSAGE = 10008
    UNKNOWN_PERMISSION_OVERWRITE = 10009
    UNKNOWN_PROVIDER = 10010
    UNKNOWN_ROLE = 10011
    UNKNOWN_TOKEN = 10012
    UNKNOWN_USER = 10013
    UNKNOWN_EMOJI = 10014
    UNKNOWN_WEBHOOK = 10015
    UNKNOWN_INTERACTION = 10062
    UNKNOWN_APPLICATION_COMMAND_PERMISSIONS = 10066
    CHANNEL_WRITE_RATE_LIMIT = 20028
    MAXIMUM_GUILD_ROLES = 30005
    MAXIMUM_WEBHOOKS = 30007
    MAXIMUM_GUILD_CHANNELS = 30013
    MAXIMUM_DAILY_APPLICATION_COMMAND_CREATES = 30034
    MAXIMUM_NON_MEMBER_BANS = 30035
    UNAUTHORIZED = 40001
    REQUEST_ENTITY_TOO_LARGE = 40005
    INTERACTION_ALREADY_ACKNOWLEDGED = 40060
    MISSING_ACCESS = 50001
    CANNOT_EDIT_OTHER_USERS_MESSAGE = 50005
    CANNOT_SEND_EMPTY_MESSAGE = 50006
    CANNOT_SEND_MESSAGES_TO_USER = 50007
    MISSING_PERMISSIONS = 50013
    INVALID_AUTHENTICATION_TOKEN = 50014
    CANNOT_EXECUTE_ON_SYSTEM_MESSAGE = 50021
    CANNOT_EXECUTE_ON_CHANNEL_TYPE = 50024
    INVALID_WEBHOOK_TOKEN = 50027
    INVALID_FORM_BODY = 50035
    THREAD_ARCHIVED = 50083
    NOT_ENOUGH_BOOSTS = 50101
    INDEX_NOT_YET_AVAILABLE = 110000
    RESOURCE_OVERLOADED = 130000
    CANNOT_REPLY_WITHOUT_READ_MESSAGE_HISTORY = 160002
    THREAD_ALREADY_CREATED = 160004
    THREAD_LOCKED = 160005


class ErrorResponse(Payload):
    """The JSON body of a failed HTTP request.

    `errors` is a tree keyed by request field paths whose leaves are `{"_errors": [...]}` lists. It is
    kept raw here and flattened by `shoal.rest.errors.flatten_errors`.

    Discord: https://docs.discord.com/developers/reference#error-messages
    """

    code: JSONErrorCode
    message: str
    errors: Raw | UnsetType = UNSET
