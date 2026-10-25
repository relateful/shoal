"""The HTTP client.

`RestClient` works on its own: it needs a token, not a gateway connection or a cache. That makes it the
same object a bot, a background worker and a dashboard backend use, and with a `Token.bearer` it calls
the API on behalf of an OAuth2 user.

Discord: https://docs.discord.com/developers/reference#http-api
"""

import logging
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus
from types import TracebackType
from typing import Literal, Self, final, overload, override
from urllib.parse import quote, urlencode

import msgspec

from shoal.core.backoff import backoff_delay
from shoal.core.clock import Clock, SystemClock
from shoal.core.codec import decode_json, encode_json
from shoal.core.metrics import (
    REST_RATE_LIMITED,
    REST_REQUEST_SECONDS,
    REST_REQUESTS,
    REST_RETRIES,
    Metrics,
    NoopMetrics,
)
from shoal.payloads.api import API_BASE_URL, API_VERSION, AUDIT_LOG_REASON_MAX_LENGTH
from shoal.payloads.application_commands import (
    ApplicationCommand,
    BulkApplicationCommandParams,
    CreateGlobalApplicationCommandParams,
    CreateGuildApplicationCommandParams,
    EditApplicationCommandPermissionsParams,
    EditGlobalApplicationCommandParams,
    EditGuildApplicationCommandParams,
    GuildApplicationCommandPermissions,
)
from shoal.payloads.channel import Channel
from shoal.payloads.gateway import GatewayBot, GatewayInfo
from shoal.payloads.guild import Guild, GuildMember
from shoal.payloads.interactions import (
    CreateFollowupMessageParams,
    InteractionCallbackResponse,
    InteractionResponse,
)
from shoal.payloads.message import (
    CreateMessageParams,
    Message,
    SearchGuildMessagesParams,
    SearchGuildMessagesResponse,
    SearchIndexNotReady,
)
from shoal.payloads.rate_limits import RateLimitResponse
from shoal.payloads.user import User
from shoal.payloads.webhook import EditWebhookMessageParams
from shoal.rest.defaults import (
    DEFAULT_USER_AGENT,
    MAX_RATE_LIMIT_WAIT,
    MAX_RETRIES,
    RETRY_BACKOFF_CAP,
    RETRYABLE_STATUSES,
    SEARCH_INDEX_RETRY_DELAY,
)
from shoal.rest.endpoints import (
    BULK_OVERWRITE_GLOBAL_APPLICATION_COMMANDS,
    BULK_OVERWRITE_GUILD_APPLICATION_COMMANDS,
    CREATE_FOLLOWUP_MESSAGE,
    CREATE_GLOBAL_APPLICATION_COMMAND,
    CREATE_GUILD_APPLICATION_COMMAND,
    CREATE_INTERACTION_RESPONSE,
    CREATE_MESSAGE,
    DELETE_FOLLOWUP_MESSAGE,
    DELETE_GLOBAL_APPLICATION_COMMAND,
    DELETE_GUILD_APPLICATION_COMMAND,
    DELETE_MESSAGE,
    DELETE_ORIGINAL_INTERACTION_RESPONSE,
    EDIT_APPLICATION_COMMAND_PERMISSIONS,
    EDIT_FOLLOWUP_MESSAGE,
    EDIT_GLOBAL_APPLICATION_COMMAND,
    EDIT_GUILD_APPLICATION_COMMAND,
    EDIT_ORIGINAL_INTERACTION_RESPONSE,
    GET_APPLICATION_COMMAND_PERMISSIONS,
    GET_CHANNEL,
    GET_CHANNEL_MESSAGE,
    GET_CURRENT_USER,
    GET_FOLLOWUP_MESSAGE,
    GET_GATEWAY,
    GET_GATEWAY_BOT,
    GET_GLOBAL_APPLICATION_COMMAND,
    GET_GLOBAL_APPLICATION_COMMANDS,
    GET_GUILD,
    GET_GUILD_APPLICATION_COMMAND,
    GET_GUILD_APPLICATION_COMMAND_PERMISSIONS,
    GET_GUILD_APPLICATION_COMMANDS,
    GET_GUILD_MEMBER,
    GET_ORIGINAL_INTERACTION_RESPONSE,
    GET_USER,
    SEARCH_GUILD_MESSAGES,
)
from shoal.rest.errors import (
    ClientClosedError,
    HTTPError,
    RateLimitedError,
    SearchIndexNotReadyError,
    TokenInvalidatedError,
)
from shoal.rest.ratelimit import LocalRateLimiter, RateLimiter, RateLimitHeaders
from shoal.rest.route import CompiledRoute
from shoal.rest.transport import AiohttpTransport, HTTPResponse, HTTPTransport, TransportError

_log = logging.getLogger("shoal.rest")


type QueryScalar = str | int | bool
"""One query string value. Booleans are sent as `true`/`false` and snowflakes as their digits.

Discord: https://docs.discord.com/developers/reference#boolean-query-strings
"""

type QueryValue = QueryScalar | Sequence[QueryScalar]
"""A query string value; a sequence is sent as the same parameter repeated (`?id=1&id=2`).

Discord: https://docs.discord.com/developers/reference#array-query-strings
"""


class TokenType(StrEnum):
    """The `Authorization` scheme.

    Discord: https://docs.discord.com/developers/reference#authentication
    """

    BOT = "Bot"
    BEARER = "Bearer"


@final
@dataclass(frozen=True, slots=True)
class Token:
    """A credential for the `Authorization` header. Its `repr` never shows the secret.

    Discord: https://docs.discord.com/developers/reference#authentication
    """

    type: TokenType
    secret: str

    @classmethod
    def bot(cls, secret: str) -> Self:
        """A bot token from the Developer Portal."""
        return cls(TokenType.BOT, secret.removeprefix("Bot ").strip())

    @classmethod
    def bearer(cls, secret: str) -> Self:
        """An OAuth2 access token, for acting as a user (dashboards, account linking)."""
        return cls(TokenType.BEARER, secret.removeprefix("Bearer ").strip())

    @property
    def header(self) -> str:
        """The `Authorization` header value."""
        return f"{self.type} {self.secret}"

    @override
    def __repr__(self) -> str:
        return f"Token(type={self.type.value}, secret=<hidden>)"


def _query_scalar(value: QueryScalar) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _encode_query(query: Mapping[str, QueryValue]) -> str:
    pairs: list[tuple[str, str]] = []
    for key, value in query.items():
        if isinstance(value, str | int):
            pairs.append((key, _query_scalar(value)))
        else:
            pairs.extend((key, _query_scalar(item)) for item in value)
    return urlencode(pairs)


def _query_of(params: msgspec.Struct) -> dict[str, QueryValue]:
    """The set fields of a query payload, ready for `_encode_query`."""
    query: dict[str, QueryValue] = {}
    for field in msgspec.structs.fields(params):
        value: object = getattr(params, field.name)
        if value is msgspec.UNSET:
            continue
        query[field.encode_name] = msgspec.convert(value, QueryValue)
    return query


class RestClient:
    """An async client for Discord's HTTP API.

    Args:
        token: The credential, or `None` for the few unauthenticated endpoints.
        transport: How requests are sent. Defaults to `AiohttpTransport`.
        rate_limiter: Defaults to a `LocalRateLimiter`. Pass a shared limiter when several processes
            use one token.
        base_url: The API base without version. Point it at a REST proxy to centralise rate limits.
        api_version: The API version segment.
        max_retries: Retries for rate limits, idempotent requests that hit 5xx, and network errors.
            A request that is not idempotent is retried after a network error only when it never
            left the machine, so a message or an interaction response is never sent twice.
        max_rate_limit_wait: The longest 429 wait, in seconds, the client will sit through before
            raising `RateLimitedError` instead.
        refuse_after_unauthorized: After a 401 on a bot token, refuse every further request. This
            protects the IP from Discord's invalid request ban when a token is revoked.
        user_agent: The `User-Agent` header. Discord requires the `DiscordBot (url, version)` shape.
        metrics: Where request, retry and rate limit metrics go. Defaults to discarding them.
        clock: Time source, for tests.
        random_source: Random source for retry jitter, for tests.

    Discord: https://docs.discord.com/developers/reference#http-api
    """

    __slots__ = (
        "_base_url",
        "_clock",
        "_closed",
        "_limiter",
        "_max_rate_limit_wait",
        "_max_retries",
        "_metrics",
        "_random_source",
        "_refuse_after_unauthorized",
        "_token",
        "_token_invalid",
        "_transport",
        "_user_agent",
    )

    def __init__(
        self,
        token: Token | None,
        *,
        transport: HTTPTransport | None = None,
        rate_limiter: RateLimiter | None = None,
        base_url: str = API_BASE_URL,
        api_version: int = API_VERSION,
        max_retries: int = MAX_RETRIES,
        max_rate_limit_wait: float = MAX_RATE_LIMIT_WAIT,
        refuse_after_unauthorized: bool = True,
        user_agent: str = DEFAULT_USER_AGENT,
        metrics: Metrics | None = None,
        clock: Clock | None = None,
        random_source: random.Random | None = None,
    ) -> None:
        """Create a client; see the class docstring for the arguments."""
        if max_retries < 0:
            msg = "max_retries cannot be negative"
            raise ValueError(msg)
        self._token: Token | None = token
        self._clock: Clock = clock or SystemClock()
        self._random_source: random.Random = random_source or random.Random()  # noqa: S311 - jitter, not security
        self._transport: HTTPTransport = transport or AiohttpTransport()
        self._metrics: Metrics = metrics or NoopMetrics()
        self._limiter: RateLimiter = rate_limiter or LocalRateLimiter(
            clock=self._clock, metrics=self._metrics
        )
        self._base_url: str = f"{base_url.rstrip('/')}/v{api_version}"
        self._max_retries: int = max_retries
        self._max_rate_limit_wait: float = max_rate_limit_wait
        self._refuse_after_unauthorized: bool = refuse_after_unauthorized
        self._user_agent: str = user_agent
        self._token_invalid: bool = False
        self._closed: bool = False

    @property
    def base_url(self) -> str:
        """The versioned base URL requests are sent to."""
        return self._base_url

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the transport. The client cannot be used afterwards."""
        if not self._closed:
            self._closed = True
            await self._transport.close()

    async def request[T](
        self,
        route: CompiledRoute,
        response_type: type[T],
        *,
        body: object = None,
        query: Mapping[str, QueryValue] | None = None,
        reason: str | None = None,
    ) -> T:
        """Send a request and decode the JSON response into `response_type`.

        Args:
            route: The compiled route.
            response_type: The payload type the endpoint returns.
            body: A payload (or any msgspec-encodable value) to send as JSON.
            query: Query string parameters.
            reason: Audit log reason, sent URL-encoded in `X-Audit-Log-Reason`
                (https://docs.discord.com/developers/resources/audit-log#audit-log-entry-object).

        Raises:
            HTTPError: Discord returned an error status (see its subclasses).
            TokenInvalidatedError: An earlier request got a 401 and the client now refuses requests.
            ClientClosedError: The client was closed.
            OSError: The network failed on every attempt.
        """
        response = await self._send(route, body=body, query=query, reason=reason)
        return decode_json(response.body, response_type)

    async def request_empty(
        self,
        route: CompiledRoute,
        *,
        body: object = None,
        query: Mapping[str, QueryValue] | None = None,
        reason: str | None = None,
    ) -> None:
        """Send a request whose successful response has no body (204). Raises like `request`."""
        await self._send(route, body=body, query=query, reason=reason)

    async def _send(
        self,
        route: CompiledRoute,
        *,
        body: object,
        query: Mapping[str, QueryValue] | None,
        reason: str | None,
    ) -> HTTPResponse:
        if self._closed:
            raise ClientClosedError
        if self._token_invalid:
            raise TokenInvalidatedError
        url = f"{self._base_url}{route.path}"
        if query:
            url = f"{url}?{_encode_query(query)}"
        headers = self._headers(reason)
        payload: bytes | None = None
        if body is not None:
            payload = encode_json(body)
            headers["Content-Type"] = "application/json"
        attempt = 0
        while True:
            outcome = await self._attempt(route, url, headers, payload, attempt)
            attempt += 1
            if isinstance(outcome, HTTPResponse):
                return outcome
            await self._clock.sleep(outcome)

    async def _attempt(
        self,
        route: CompiledRoute,
        url: str,
        headers: Mapping[str, str],
        payload: bytes | None,
        attempt: int,
    ) -> HTTPResponse | float:
        """Send once. Returns the successful response, or the delay before retrying; raises otherwise."""
        template = route.route.key
        await self._limiter.acquire(route)
        started = self._clock.monotonic()
        try:
            response = await self._transport.request(route.method, url, headers=headers, body=payload)
        except OSError as error:
            self._limiter.release(route, None, None, None)
            if attempt >= self._max_retries or (
                not route.method.is_idempotent and _may_have_been_sent(error)
            ):
                error.add_note(f"route: {route.method} {route.display}")
                raise
            delay = backoff_delay(attempt + 1, cap=RETRY_BACKOFF_CAP, random_source=self._random_source)
            self._metrics.increment(REST_RETRIES, {"route": template, "reason": "network"})
            _log.warning(
                "%s %s failed at the network level; retrying in %.2fs", route.method, route.display, delay
            )
            return delay
        except BaseException:
            # Cancelled (a caller's timeout): the bucket must still learn the request is over, or
            # every later request on it waits forever.
            self._limiter.release(route, None, None, None)
            raise

        limits = RateLimitHeaders.parse(response.headers)
        rate_limited = response.status == HTTPStatus.TOO_MANY_REQUESTS
        retry_after = self._retry_after(response) if rate_limited else None
        self._limiter.release(route, response.status, limits, retry_after)

        labels = {"method": route.method.value, "route": template}
        self._metrics.observe(REST_REQUEST_SECONDS, self._clock.monotonic() - started, labels)
        self._metrics.increment(REST_REQUESTS, {**labels, "status": str(response.status)})
        if HTTPStatus.OK <= response.status < HTTPStatus.MULTIPLE_CHOICES:
            return response
        if (
            response.status == HTTPStatus.UNAUTHORIZED
            and self._refuse_after_unauthorized
            and self._is_bot_token
        ):
            self._token_invalid = True
            _log.error("bot token rejected (401); refusing further requests to avoid an IP ban")
        if retry_after is not None:
            scope = limits.scope.value if limits.scope is not None else "unknown"
            self._metrics.increment(REST_RATE_LIMITED, {"route": template, "scope": scope})
            if attempt >= self._max_retries or retry_after > self._max_rate_limit_wait:
                raise RateLimitedError(route, response.status, f"rate limited for {retry_after:.2f}s")
            self._metrics.increment(REST_RETRIES, {"route": template, "reason": "rate_limited"})
            _log.info("%s %s rate limited for %.2fs; retrying", route.method, route.display, retry_after)
            return 0.0
        if (
            response.status in RETRYABLE_STATUSES
            and route.method.is_idempotent
            and attempt < self._max_retries
        ):
            delay = backoff_delay(attempt + 1, cap=RETRY_BACKOFF_CAP, random_source=self._random_source)
            self._metrics.increment(REST_RETRIES, {"route": template, "reason": "server_error"})
            _log.warning(
                "%s %s returned %d; retrying in %.2fs", route.method, route.display, response.status, delay
            )
            return delay
        raise HTTPError.from_response(route, response.status, response.body)

    @property
    def _is_bot_token(self) -> bool:
        return self._token is not None and self._token.type is TokenType.BOT

    def _headers(self, reason: str | None) -> dict[str, str]:
        headers = {"User-Agent": self._user_agent}
        if self._token is not None:
            headers["Authorization"] = self._token.header
        if reason:
            headers["X-Audit-Log-Reason"] = quote(reason[:AUDIT_LOG_REASON_MAX_LENGTH], safe=" ")
        return headers

    @staticmethod
    def _retry_after(response: HTTPResponse) -> float:
        try:
            return max(msgspec.json.decode(response.body, type=RateLimitResponse).retry_after, 0.0)
        except (msgspec.DecodeError, msgspec.ValidationError):
            header = response.headers.get("retry-after", "1")
            try:
                return max(float(header), 0.0)
            except ValueError:
                return 1.0

    async def get_gateway(self) -> GatewayInfo:
        """Get the gateway URL. Needs no token.

        Discord: https://docs.discord.com/developers/events/gateway#get-gateway
        """
        return await self.request(GET_GATEWAY.compile(), GatewayInfo)

    async def get_gateway_bot(self) -> GatewayBot:
        """Get the gateway URL, recommended shard count and session start limit.

        Discord: https://docs.discord.com/developers/events/gateway#get-gateway-bot
        """
        return await self.request(GET_GATEWAY_BOT.compile(), GatewayBot)

    async def get_current_user(self) -> User:
        """Get the user the token belongs to (the bot, or the OAuth2 user for a bearer token).

        Discord: https://docs.discord.com/developers/resources/user#get-current-user
        """
        return await self.request(GET_CURRENT_USER.compile(), User)

    async def get_user(self, user_id: int) -> User:
        """Get any user by ID.

        Discord: https://docs.discord.com/developers/resources/user#get-user
        """
        return await self.request(GET_USER.compile(user_id=user_id), User)

    async def get_channel(self, channel_id: int) -> Channel:
        """Get a channel or thread by ID.

        Discord: https://docs.discord.com/developers/resources/channel#get-channel
        """
        return await self.request(GET_CHANNEL.compile(channel_id=channel_id), Channel)

    async def get_guild(self, guild_id: int, *, with_counts: bool = False) -> Guild:
        """Get a guild, optionally with approximate member and presence counts.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild
        """
        return await self.request(
            GET_GUILD.compile(guild_id=guild_id), Guild, query={"with_counts": with_counts}
        )

    async def get_guild_member(self, guild_id: int, user_id: int) -> GuildMember:
        """Get one member of a guild.

        Discord: https://docs.discord.com/developers/resources/guild#get-guild-member
        """
        return await self.request(GET_GUILD_MEMBER.compile(guild_id=guild_id, user_id=user_id), GuildMember)

    async def get_channel_message(self, channel_id: int, message_id: int) -> Message:
        """Get one message.

        Discord: https://docs.discord.com/developers/resources/message#get-channel-message
        """
        return await self.request(
            GET_CHANNEL_MESSAGE.compile(channel_id=channel_id, message_id=message_id), Message
        )

    async def create_message(self, channel_id: int, params: CreateMessageParams) -> Message:
        """Send a message.

        Discord: https://docs.discord.com/developers/resources/message#create-message
        """
        return await self.request(CREATE_MESSAGE.compile(channel_id=channel_id), Message, body=params)

    async def search_guild_messages(
        self, guild_id: int, params: SearchGuildMessagesParams
    ) -> SearchGuildMessagesResponse:
        """Search a guild's messages. Needs the Message Content intent and Read Message History.

        While Discord is still indexing the guild it answers `202 Accepted`; the client waits the
        `retry_after` Discord gives and tries again, within `max_retries`.

        Raises:
            SearchIndexNotReadyError: The index was still not ready after every retry.

        Discord: https://docs.discord.com/developers/resources/message#search-guild-messages
        """
        route = SEARCH_GUILD_MESSAGES.compile(guild_id=guild_id)
        query = _query_of(params)
        attempt = 0
        while True:
            response = await self._send(route, body=None, query=query, reason=None)
            if response.status != HTTPStatus.ACCEPTED:
                return decode_json(response.body, SearchGuildMessagesResponse)
            pending = decode_json(response.body, SearchIndexNotReady)
            if attempt >= self._max_retries:
                raise SearchIndexNotReadyError(pending.documents_indexed, pending.retry_after)
            attempt += 1
            await self._clock.sleep(pending.retry_after or SEARCH_INDEX_RETRY_DELAY)

    async def delete_message(self, channel_id: int, message_id: int, *, reason: str | None = None) -> None:
        """Delete a message.

        Discord: https://docs.discord.com/developers/resources/message#delete-message
        """
        await self.request_empty(
            DELETE_MESSAGE.compile(channel_id=channel_id, message_id=message_id), reason=reason
        )

    async def get_global_application_commands(
        self, application_id: int, *, with_localizations: bool = False
    ) -> list[ApplicationCommand]:
        """Get the app's global commands.

        Without `with_localizations`, Discord sends each name and description in the requester's
        locale (`name_localized`) instead of the full dictionaries.

        Discord: https://docs.discord.com/developers/interactions/application-commands#get-global-application-commands
        """
        return await self.request(
            GET_GLOBAL_APPLICATION_COMMANDS.compile(application_id=application_id),
            list[ApplicationCommand],
            query={"with_localizations": with_localizations},
        )

    async def create_global_application_command(
        self, application_id: int, params: CreateGlobalApplicationCommandParams
    ) -> ApplicationCommand:
        """Create a global command, replacing one with the same name.

        Discord: https://docs.discord.com/developers/interactions/application-commands#create-global-application-command
        """
        return await self.request(
            CREATE_GLOBAL_APPLICATION_COMMAND.compile(application_id=application_id),
            ApplicationCommand,
            body=params,
        )

    async def get_global_application_command(
        self, application_id: int, command_id: int
    ) -> ApplicationCommand:
        """Get one global command.

        Discord: https://docs.discord.com/developers/interactions/application-commands#get-global-application-command
        """
        return await self.request(
            GET_GLOBAL_APPLICATION_COMMAND.compile(application_id=application_id, command_id=command_id),
            ApplicationCommand,
        )

    async def edit_global_application_command(
        self, application_id: int, command_id: int, params: EditGlobalApplicationCommandParams
    ) -> ApplicationCommand:
        """Edit a global command; the fields given replace the existing values.

        Discord: https://docs.discord.com/developers/interactions/application-commands#edit-global-application-command
        """
        return await self.request(
            EDIT_GLOBAL_APPLICATION_COMMAND.compile(application_id=application_id, command_id=command_id),
            ApplicationCommand,
            body=params,
        )

    async def delete_global_application_command(self, application_id: int, command_id: int) -> None:
        """Delete a global command.

        Discord: https://docs.discord.com/developers/interactions/application-commands#delete-global-application-command
        """
        await self.request_empty(
            DELETE_GLOBAL_APPLICATION_COMMAND.compile(application_id=application_id, command_id=command_id)
        )

    async def bulk_overwrite_global_application_commands(
        self, application_id: int, commands: Sequence[BulkApplicationCommandParams]
    ) -> list[ApplicationCommand]:
        """Replace every global command (slash, user and message) with `commands`.

        Commands not in the list are deleted; an empty list deletes them all.

        Discord: https://docs.discord.com/developers/interactions/application-commands#bulk-overwrite-global-application-commands
        """
        return await self.request(
            BULK_OVERWRITE_GLOBAL_APPLICATION_COMMANDS.compile(application_id=application_id),
            list[ApplicationCommand],
            body=list(commands),
        )

    async def get_guild_application_commands(
        self, application_id: int, guild_id: int, *, with_localizations: bool = False
    ) -> list[ApplicationCommand]:
        """Get the app's commands in one guild.

        Discord: https://docs.discord.com/developers/interactions/application-commands#get-guild-application-commands
        """
        return await self.request(
            GET_GUILD_APPLICATION_COMMANDS.compile(application_id=application_id, guild_id=guild_id),
            list[ApplicationCommand],
            query={"with_localizations": with_localizations},
        )

    async def create_guild_application_command(
        self, application_id: int, guild_id: int, params: CreateGuildApplicationCommandParams
    ) -> ApplicationCommand:
        """Create a guild command, available immediately, replacing one with the same name.

        Discord: https://docs.discord.com/developers/interactions/application-commands#create-guild-application-command
        """
        return await self.request(
            CREATE_GUILD_APPLICATION_COMMAND.compile(application_id=application_id, guild_id=guild_id),
            ApplicationCommand,
            body=params,
        )

    async def get_guild_application_command(
        self, application_id: int, guild_id: int, command_id: int
    ) -> ApplicationCommand:
        """Get one guild command.

        Discord: https://docs.discord.com/developers/interactions/application-commands#get-guild-application-command
        """
        return await self.request(
            GET_GUILD_APPLICATION_COMMAND.compile(
                application_id=application_id, guild_id=guild_id, command_id=command_id
            ),
            ApplicationCommand,
        )

    async def edit_guild_application_command(
        self, application_id: int, guild_id: int, command_id: int, params: EditGuildApplicationCommandParams
    ) -> ApplicationCommand:
        """Edit a guild command; the fields given replace the existing values.

        Discord: https://docs.discord.com/developers/interactions/application-commands#edit-guild-application-command
        """
        return await self.request(
            EDIT_GUILD_APPLICATION_COMMAND.compile(
                application_id=application_id, guild_id=guild_id, command_id=command_id
            ),
            ApplicationCommand,
            body=params,
        )

    async def delete_guild_application_command(
        self, application_id: int, guild_id: int, command_id: int
    ) -> None:
        """Delete a guild command.

        Discord: https://docs.discord.com/developers/interactions/application-commands#delete-guild-application-command
        """
        await self.request_empty(
            DELETE_GUILD_APPLICATION_COMMAND.compile(
                application_id=application_id, guild_id=guild_id, command_id=command_id
            )
        )

    async def bulk_overwrite_guild_application_commands(
        self, application_id: int, guild_id: int, commands: Sequence[BulkApplicationCommandParams]
    ) -> list[ApplicationCommand]:
        """Replace every command of the app in one guild with `commands`.

        Discord: https://docs.discord.com/developers/interactions/application-commands#bulk-overwrite-guild-application-commands
        """
        return await self.request(
            BULK_OVERWRITE_GUILD_APPLICATION_COMMANDS.compile(
                application_id=application_id, guild_id=guild_id
            ),
            list[ApplicationCommand],
            body=list(commands),
        )

    async def get_guild_application_command_permissions(
        self, application_id: int, guild_id: int
    ) -> list[GuildApplicationCommandPermissions]:
        """Get the permission overwrites of every command of the app in one guild.

        Discord: https://docs.discord.com/developers/interactions/application-commands#get-guild-application-command-permissions
        """
        return await self.request(
            GET_GUILD_APPLICATION_COMMAND_PERMISSIONS.compile(
                application_id=application_id, guild_id=guild_id
            ),
            list[GuildApplicationCommandPermissions],
        )

    async def get_application_command_permissions(
        self, application_id: int, guild_id: int, command_id: int
    ) -> GuildApplicationCommandPermissions:
        """Get the permission overwrites of one command in one guild.

        Discord: https://docs.discord.com/developers/interactions/application-commands#get-application-command-permissions
        """
        return await self.request(
            GET_APPLICATION_COMMAND_PERMISSIONS.compile(
                application_id=application_id, guild_id=guild_id, command_id=command_id
            ),
            GuildApplicationCommandPermissions,
        )

    async def edit_application_command_permissions(
        self,
        application_id: int,
        guild_id: int,
        command_id: int,
        params: EditApplicationCommandPermissionsParams,
    ) -> GuildApplicationCommandPermissions:
        """Replace the permission overwrites of one command in one guild.

        Needs a client built with `Token.bearer` for a user who can manage the guild and its roles; a
        bot token is rejected.

        Discord: https://docs.discord.com/developers/interactions/application-commands#edit-application-command-permissions
        """
        return await self.request(
            EDIT_APPLICATION_COMMAND_PERMISSIONS.compile(
                application_id=application_id, guild_id=guild_id, command_id=command_id
            ),
            GuildApplicationCommandPermissions,
            body=params,
        )

    @overload
    async def create_interaction_response(
        self,
        interaction_id: int,
        interaction_token: str,
        response: InteractionResponse,
        *,
        with_response: Literal[False] = False,
    ) -> None: ...

    @overload
    async def create_interaction_response(
        self,
        interaction_id: int,
        interaction_token: str,
        response: InteractionResponse,
        *,
        with_response: Literal[True],
    ) -> InteractionCallbackResponse: ...

    @overload
    async def create_interaction_response(
        self,
        interaction_id: int,
        interaction_token: str,
        response: InteractionResponse,
        *,
        with_response: bool,
    ) -> InteractionCallbackResponse | None: ...

    async def create_interaction_response(
        self,
        interaction_id: int,
        interaction_token: str,
        response: InteractionResponse,
        *,
        with_response: bool = False,
    ) -> InteractionCallbackResponse | None:
        """Answer an interaction. Must happen within 3 seconds of receiving it, and only once.

        With `with_response`, Discord returns what the response created (the message, or the
        launched Activity).

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#create-interaction-response
        """
        route = CREATE_INTERACTION_RESPONSE.compile(
            interaction_id=interaction_id, interaction_token=interaction_token
        )
        if with_response:
            return await self.request(
                route, InteractionCallbackResponse, body=response, query={"with_response": True}
            )
        await self.request_empty(route, body=response)
        return None

    async def get_original_interaction_response(self, application_id: int, interaction_token: str) -> Message:
        """Get the message an interaction response created.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#get-original-interaction-response
        """
        return await self.request(
            GET_ORIGINAL_INTERACTION_RESPONSE.compile(
                application_id=application_id, interaction_token=interaction_token
            ),
            Message,
        )

    async def edit_original_interaction_response(
        self, application_id: int, interaction_token: str, params: EditWebhookMessageParams
    ) -> Message:
        """Edit the message an interaction response created, or fill in a deferred one.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#edit-original-interaction-response
        """
        return await self.request(
            EDIT_ORIGINAL_INTERACTION_RESPONSE.compile(
                application_id=application_id, interaction_token=interaction_token
            ),
            Message,
            body=params,
        )

    async def delete_original_interaction_response(self, application_id: int, interaction_token: str) -> None:
        """Delete the message an interaction response created.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#delete-original-interaction-response
        """
        await self.request_empty(
            DELETE_ORIGINAL_INTERACTION_RESPONSE.compile(
                application_id=application_id, interaction_token=interaction_token
            )
        )

    async def create_followup_message(
        self, application_id: int, interaction_token: str, params: CreateFollowupMessageParams
    ) -> Message:
        """Send another message for an interaction, for up to 15 minutes after it.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#create-followup-message
        """
        return await self.request(
            CREATE_FOLLOWUP_MESSAGE.compile(
                application_id=application_id, interaction_token=interaction_token
            ),
            Message,
            body=params,
        )

    async def get_followup_message(
        self, application_id: int, interaction_token: str, message_id: int
    ) -> Message:
        """Get a follow-up message.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#get-followup-message
        """
        return await self.request(
            GET_FOLLOWUP_MESSAGE.compile(
                application_id=application_id, interaction_token=interaction_token, message_id=message_id
            ),
            Message,
        )

    async def edit_followup_message(
        self, application_id: int, interaction_token: str, message_id: int, params: EditWebhookMessageParams
    ) -> Message:
        """Edit a follow-up message.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#edit-followup-message
        """
        return await self.request(
            EDIT_FOLLOWUP_MESSAGE.compile(
                application_id=application_id, interaction_token=interaction_token, message_id=message_id
            ),
            Message,
            body=params,
        )

    async def delete_followup_message(
        self, application_id: int, interaction_token: str, message_id: int
    ) -> None:
        """Delete a follow-up message.

        Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#delete-followup-message
        """
        await self.request_empty(
            DELETE_FOLLOWUP_MESSAGE.compile(
                application_id=application_id, interaction_token=interaction_token, message_id=message_id
            )
        )


def _may_have_been_sent(error: OSError) -> bool:
    """Whether Discord could have received (and acted on) a request that failed with `error`."""
    if isinstance(error, TransportError):
        return error.request_sent
    return not isinstance(error, ConnectionRefusedError)
