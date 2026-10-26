"""The HTTP client.

`RestClient` works on its own: it needs a token, not a gateway connection or a cache. That makes it the
same object a bot, a background worker and a dashboard backend use, and with a `Token.bearer` it calls
the API on behalf of an OAuth2 user.

Discord: https://docs.discord.com/developers/reference#http-api
"""

import logging
import random
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus
from types import TracebackType
from typing import Self, final, override
from urllib.parse import quote

from shoal.core.backoff import backoff_delay
from shoal.core.clock import Clock, SystemClock
from shoal.core.codec import PayloadDecodeError, decode_json, encode_json
from shoal.core.metrics import (
    REST_RATE_LIMITED,
    REST_REQUEST_SECONDS,
    REST_REQUESTS,
    REST_RETRIES,
    Metrics,
    NoopMetrics,
)
from shoal.payloads.api import API_BASE_URL, API_VERSION, AUDIT_LOG_REASON_MAX_LENGTH
from shoal.payloads.message import SearchIndexNotReady
from shoal.rest.defaults import (
    DEFAULT_USER_AGENT,
    MAX_RATE_LIMIT_WAIT,
    MAX_RETRIES,
    PROXY_SECRET_HEADER,
    RETRY_BACKOFF_CAP,
    RETRYABLE_STATUSES,
    SEARCH_INDEX_RETRY_DELAY,
)
from shoal.rest.errors import (
    ClientClosedError,
    HTTPError,
    RateLimitedError,
    SearchIndexNotReadyError,
    TokenInvalidatedError,
)
from shoal.rest.files import File, encode_multipart
from shoal.rest.ratelimit import LocalRateLimiter, RateLimiter, WaitTooLongError, rate_limit_of
from shoal.rest.requester import QueryValue, Requester, encode_query
from shoal.rest.resources import (
    Applications,
    AuditLogs,
    AutoMod,
    Channels,
    Commands,
    Emojis,
    Entitlements,
    Gateway,
    Guilds,
    Identities,
    Interactions,
    Invites,
    Lobbies,
    Members,
    Messages,
    OAuth2,
    Polls,
    Reactions,
    RoleConnections,
    Roles,
    ScheduledEvents,
    SKUs,
    Soundboard,
    StageInstances,
    Stickers,
    Subscriptions,
    Templates,
    Threads,
    Users,
    Voice,
    VoiceStates,
    Webhooks,
)
from shoal.rest.route import CompiledRoute
from shoal.rest.transport import AiohttpTransport, HTTPResponse, HTTPTransport, TransportError

_log = logging.getLogger("shoal.rest")


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


class RestClient(Requester):
    """An async client for Discord's HTTP API.

    Endpoints are grouped by resource, one attribute each: `rest.messages.create(...)`,
    `rest.members.ban(...)`, `rest.interactions.respond(...)`. The classes live in
    `shoal.rest.resources`.

    Args:
        token: The credential, or `None` for the few unauthenticated endpoints.
        transport: How requests are sent. Defaults to `AiohttpTransport`.
        rate_limiter: Defaults to a `LocalRateLimiter`. Pass a shared limiter when several processes
            use one token.
        base_url: The API base without version. Point it at a REST proxy to centralise rate limits.
        proxy_secret: The secret a `RestProxy` expects, sent with every request when given.
        api_version: The API version segment.
        max_retries: Retries for rate limits, idempotent requests that hit 5xx, and network errors.
            A request that is not idempotent is retried after a network error only when it never
            left the machine, so a message or an interaction response is never sent twice.
        max_rate_limit_wait: The longest rate limit wait, in seconds (a 429's, or a bucket, global or
            invalid request hold before sending), the client will sit through before
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
        "_proxy_secret",
        "_random_source",
        "_refuse_after_unauthorized",
        "_token",
        "_token_invalid",
        "_transport",
        "_user_agent",
        "applications",
        "audit_logs",
        "automod",
        "channels",
        "commands",
        "emojis",
        "entitlements",
        "gateway",
        "guilds",
        "identities",
        "interactions",
        "invites",
        "lobbies",
        "members",
        "messages",
        "oauth2",
        "polls",
        "reactions",
        "role_connections",
        "roles",
        "scheduled_events",
        "skus",
        "soundboard",
        "stage_instances",
        "stickers",
        "subscriptions",
        "templates",
        "threads",
        "users",
        "voice",
        "voice_states",
        "webhooks",
    )

    def __init__(
        self,
        token: Token | None,
        *,
        transport: HTTPTransport | None = None,
        rate_limiter: RateLimiter | None = None,
        base_url: str = API_BASE_URL,
        proxy_secret: str | None = None,
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
        self._proxy_secret: str | None = proxy_secret
        self._max_retries: int = max_retries
        self._max_rate_limit_wait: float = max_rate_limit_wait
        self._refuse_after_unauthorized: bool = refuse_after_unauthorized
        self._user_agent: str = user_agent
        self._token_invalid: bool = False
        self._closed: bool = False
        self.applications: Applications = Applications(self)
        self.audit_logs: AuditLogs = AuditLogs(self)
        self.automod: AutoMod = AutoMod(self)
        self.channels: Channels = Channels(self)
        self.commands: Commands = Commands(self)
        self.emojis: Emojis = Emojis(self)
        self.entitlements: Entitlements = Entitlements(self)
        self.gateway: Gateway = Gateway(self)
        self.guilds: Guilds = Guilds(self)
        self.identities: Identities = Identities(self)
        self.interactions: Interactions = Interactions(self)
        self.invites: Invites = Invites(self)
        self.lobbies: Lobbies = Lobbies(self)
        self.members: Members = Members(self)
        self.messages: Messages = Messages(self)
        self.oauth2: OAuth2 = OAuth2(self)
        self.polls: Polls = Polls(self)
        self.reactions: Reactions = Reactions(self)
        self.role_connections: RoleConnections = RoleConnections(self)
        self.roles: Roles = Roles(self)
        self.scheduled_events: ScheduledEvents = ScheduledEvents(self)
        self.skus: SKUs = SKUs(self)
        self.soundboard: Soundboard = Soundboard(self)
        self.stage_instances: StageInstances = StageInstances(self)
        self.stickers: Stickers = Stickers(self)
        self.subscriptions: Subscriptions = Subscriptions(self)
        self.templates: Templates = Templates(self)
        self.threads: Threads = Threads(self)
        self.users: Users = Users(self)
        self.voice: Voice = Voice(self)
        self.voice_states: VoiceStates = VoiceStates(self)
        self.webhooks: Webhooks = Webhooks(self)

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

    @override
    async def request[T](
        self,
        route: CompiledRoute,
        response_type: type[T],
        *,
        body: object = None,
        query: Mapping[str, QueryValue] | None = None,
        reason: str | None = None,
        files: Mapping[str, File] | None = None,
        form: Mapping[str, str] | None = None,
    ) -> T:
        """Send a request and decode the JSON response into `response_type`.

        Args:
            route: The compiled route.
            response_type: The payload type the endpoint returns.
            body: A payload (or any msgspec-encodable value) to send as JSON.
            query: Query string parameters.
            reason: Audit log reason, sent URL-encoded in `X-Audit-Log-Reason`
                (https://docs.discord.com/developers/resources/audit-log#audit-log-entry-object).
            files: Files to upload, by form field name. The request becomes `multipart/form-data`,
                with `body` in its `payload_json` part.
            form: Plain text form fields sent next to `files`.

        Raises:
            HTTPError: Discord returned an error status (see its subclasses).
            TokenInvalidatedError: An earlier request got a 401 and the client now refuses requests.
            ClientClosedError: The client was closed.
            OSError: The network failed on every attempt.
        """
        response = await self._send(route, body=body, query=query, reason=reason, files=files, form=form)
        return _decode_success(route, response, response_type)

    @override
    async def request_empty(
        self,
        route: CompiledRoute,
        *,
        body: object = None,
        query: Mapping[str, QueryValue] | None = None,
        reason: str | None = None,
        files: Mapping[str, File] | None = None,
        form: Mapping[str, str] | None = None,
    ) -> None:
        """Send a request whose successful response has no body (204). Raises like `request`."""
        await self._send(route, body=body, query=query, reason=reason, files=files, form=form)

    @override
    async def request_optional[T](
        self,
        route: CompiledRoute,
        response_type: type[T],
        *,
        body: object = None,
        reason: str | None = None,
    ) -> T | None:
        """Send a request that may answer with no body; `None` then. Raises like `request`."""
        response = await self._send(route, body=body, query=None, reason=reason)
        return _decode_success(route, response, response_type) if response.body else None

    @override
    async def request_bytes(
        self, route: CompiledRoute, *, query: Mapping[str, QueryValue] | None = None
    ) -> bytes:
        """Send a request and return the response body undecoded. Raises like `request`."""
        response = await self._send(route, body=None, query=query, reason=None)
        return response.body

    @override
    async def request_search[T](
        self, route: CompiledRoute, response_type: type[T], *, query: Mapping[str, QueryValue]
    ) -> T:
        """Send a search request. While Discord indexes it answers `202 Accepted`; wait and retry.

        Raises:
            SearchIndexNotReadyError: The index was still not ready after `max_retries` retries.
        """
        attempt = 0
        while True:
            response = await self._send(route, body=None, query=query, reason=None)
            if response.status != HTTPStatus.ACCEPTED:
                return _decode_success(route, response, response_type)
            pending = decode_json(response.body, SearchIndexNotReady)
            if attempt >= self._max_retries:
                raise SearchIndexNotReadyError(pending.documents_indexed, pending.retry_after)
            attempt += 1
            await self._clock.sleep(pending.retry_after or SEARCH_INDEX_RETRY_DELAY)

    async def _send(
        self,
        route: CompiledRoute,
        *,
        body: object,
        query: Mapping[str, QueryValue] | None,
        reason: str | None,
        files: Mapping[str, File] | None = None,
        form: Mapping[str, str] | None = None,
    ) -> HTTPResponse:
        if self._closed:
            raise ClientClosedError
        if self._refuses(route):
            raise TokenInvalidatedError
        url = f"{self._base_url}{route.path}"
        if query:
            url = f"{url}?{encode_query(query)}"
        headers = self._headers(reason, authorize=not route.route.token_authenticated)
        payload: bytes | None = None
        if files or form:
            payload, headers["Content-Type"] = encode_multipart(
                None if body is None else encode_json(body), files or {}, form
            )
        elif body is not None:
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
        try:
            await self._limiter.acquire(route, max_wait=self._max_rate_limit_wait)
        except WaitTooLongError as error:
            # As for a 429 too long to wait out, but found out before sending.
            msg = f"rate limited for {error.seconds:.2f}s before sending"
            raise RateLimitedError(route, HTTPStatus.TOO_MANY_REQUESTS, msg) from None
        if self._refuses(route):
            # The token was rejected while this request waited for its turn or its retry.
            self._limiter.release(route, None, None, None)
            raise TokenInvalidatedError
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

        limits, retry_after = rate_limit_of(response.status, response.headers, response.body)
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
            and not route.route.token_authenticated
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

    def _refuses(self, route: CompiledRoute) -> bool:
        """Whether the bot token was rejected and `route` would send it."""
        return self._token_invalid and not route.route.token_authenticated

    def _headers(self, reason: str | None, *, authorize: bool) -> dict[str, str]:
        headers = {"User-Agent": self._user_agent}
        if self._proxy_secret is not None:
            headers[PROXY_SECRET_HEADER] = self._proxy_secret
        if authorize and self._token is not None:
            headers["Authorization"] = self._token.header
        if reason:
            headers["X-Audit-Log-Reason"] = quote(reason[:AUDIT_LOG_REASON_MAX_LENGTH], safe=" ")
        return headers


def _may_have_been_sent(error: OSError) -> bool:
    """Whether Discord could have received (and acted on) a request that failed with `error`."""
    if isinstance(error, TransportError):
        return error.request_sent
    return not isinstance(error, ConnectionRefusedError)


def _decode_success[T](route: CompiledRoute, response: HTTPResponse, response_type: type[T]) -> T:
    """Decode a successful response, noting on failure that Discord already carried out the request.

    A caller that retries on an error would otherwise repeat a request that worked: send a message
    twice, ban twice.

    Raises:
        PayloadDecodeError: The response does not match `response_type`.
    """
    try:
        return decode_json(response.body, response_type)
    except PayloadDecodeError as error:
        error.add_note(
            f"{route.method} {route.display} succeeded with HTTP {response.status}; "
            "only reading Discord's answer failed, so do not repeat the request"
        )
        raise
