"""A REST proxy: one process holds a bot's token and rate limits, and every other process sends through it.

    async with RestProxy(Token.bot(bot_token), secret=proxy_secret, host="10.0.0.5"):
        await asyncio.Event().wait()

    # in every other process: no bot token, only the proxy's secret
    rest = RestClient(None, base_url="http://10.0.0.5:8080/api", proxy_secret=proxy_secret)

Requests are matched to the route Discord documents for them and wait in the proxy's rate limiter,
so every process together stays under the bucket, global and invalid request limits, however many
there are. A request the limiter would hold longer than `max_rate_limit_wait` is answered with a 429
of the `shared` scope, which clients do not count as an invalid request. The proxy sends each request
once: a 429 or an error from Discord goes back to the caller, whose own client retries it through the
proxy.

Every request must carry the proxy's secret (`PROXY_SECRET_HEADER`, which `RestClient` sends when
given `proxy_secret`), so only the bot's own processes can send through it; the bot token stays in
the proxy, which adds it to the routes that need it. Pass `ssl` to serve HTTPS beyond one host.

Discord: https://docs.discord.com/developers/topics/rate-limits
"""

import asyncio
import hmac
import logging
import re
import string
from collections.abc import Iterable
from http import HTTPStatus
from ssl import SSLContext
from types import TracebackType
from typing import Final, Self, final
from urllib.parse import unquote

from aiohttp import web

import shoal.rest.endpoints as endpoint_routes
from shoal.core.codec import encode_json
from shoal.core.metrics import REST_RATE_LIMITED, REST_REQUESTS, Metrics, NoopMetrics
from shoal.payloads.api import API_BASE_URL
from shoal.rest.client import Token, TokenType
from shoal.rest.defaults import (
    MAX_RATE_LIMIT_WAIT,
    PROXY_HOST,
    PROXY_MAX_BODY_SIZE,
    PROXY_PATH,
    PROXY_PORT,
    PROXY_SECRET_HEADER,
)
from shoal.rest.ratelimit import LocalRateLimiter, RateLimiter, WaitTooLongError, rate_limit_of
from shoal.rest.route import CompiledRoute, HTTPMethod, Route
from shoal.rest.transport import AiohttpTransport, HTTPTransport

_log = logging.getLogger("shoal.rest")

_FORWARDED: Final = frozenset({"content-type", "user-agent", "x-audit-log-reason"})
"""Request headers passed on to Discord; the proxy sets `Authorization` itself."""

_NOT_RETURNED: Final = frozenset(
    {"connection", "content-encoding", "content-length", "keep-alive", "set-cookie", "transfer-encoding"}
)
"""Response headers kept from callers: those describing one connection (the server writes its own),
and cookies, which are the proxy's own with Discord's edge."""

_JSON: Final = "application/json"


@final
class RouteTable:
    """Finds the route Discord documents for a request's method and path.

    Args:
        routes: The routes to match; every route in `shoal.rest.endpoints` by default.
    """

    __slots__ = ("_routes",)

    def __init__(self, routes: Iterable[Route] | None = None) -> None:
        """Index `routes`; see the class docstring."""
        declared = (
            routes
            if routes is not None
            else (value for value in vars(endpoint_routes).values() if isinstance(value, Route))
        )
        self._routes: dict[HTTPMethod, list[tuple[re.Pattern[str], Route]]] = {}
        # A literal segment wins over a placeholder: `/users/@me` before `/users/{user_id}`. Paths of
        # one shape (a webhook's and an interaction follow-up's) are matched as the route counted
        # against the global limit, the safer of the two.
        for route in sorted(declared, key=lambda route: (len(route.parameters), not route.global_limit)):
            self._routes.setdefault(route.method, []).append((_pattern(route.path), route))

    def match(self, method: str, path: str) -> CompiledRoute | None:
        """The route of `method` and `path` (still percent-encoded), or `None` if none is declared."""
        try:
            candidates = self._routes.get(HTTPMethod(method), [])
        except ValueError:
            return None
        for pattern, route in candidates:
            found = pattern.fullmatch(path)
            if found is None:
                continue
            try:
                return route.compile(**{name: unquote(value) for name, value in found.groupdict().items()})
            except ValueError:
                return None  # `.` or `..`: the path would name another route
        return None


def _pattern(template: str) -> re.Pattern[str]:
    parts: list[str] = []
    for literal, name, _, _ in string.Formatter().parse(template):
        parts.append(re.escape(literal))
        if name is not None:
            parts.append(f"(?P<{name}>[^/]+)")
    return re.compile("".join(parts))


@final
class RestProxy:
    """Sends the requests of a bot's processes to Discord under one set of rate limits.

    Args:
        token: The bot's token, added to every route that needs one.
        secret: What callers prove themselves with, in `PROXY_SECRET_HEADER` on every request.
        host: Address to listen on; this machine only by default.
        port: Port to listen on; `0` picks a free one (see `address`).
        path: The path clients put before `/v{version}` (their `base_url` is `http://host:port{path}`).
        rate_limiter: The limits every request waits in; a `LocalRateLimiter` by default.
        transport: How requests reach Discord; `AiohttpTransport` by default.
        base_url: Discord's API base, without version.
        max_rate_limit_wait: The longest a request waits in the limiter before the proxy answers 429.
        max_body_size: The largest request body accepted, in bytes (attachments included).
        metrics: Receives `shoal_rest_requests_total` for every response from Discord, and
            `shoal_rest_rate_limited_total{scope="proxy"}` for every request the proxy holds back.
        ssl: Serve HTTPS with this context.

    Raises:
        ValueError: `secret` is empty.
    """

    __slots__ = (
        "_base_url",
        "_host",
        "_max_body_size",
        "_max_rate_limit_wait",
        "_metrics",
        "_path",
        "_port",
        "_prefix",
        "_rate_limiter",
        "_routes",
        "_runner",
        "_secret",
        "_ssl",
        "_start_lock",
        "_token",
        "_token_invalid",
        "_transport",
    )

    def __init__(
        self,
        token: Token,
        *,
        secret: str,
        host: str = PROXY_HOST,
        port: int = PROXY_PORT,
        path: str = PROXY_PATH,
        rate_limiter: RateLimiter | None = None,
        transport: HTTPTransport | None = None,
        base_url: str = API_BASE_URL,
        max_rate_limit_wait: float = MAX_RATE_LIMIT_WAIT,
        max_body_size: int = PROXY_MAX_BODY_SIZE,
        metrics: Metrics | None = None,
        ssl: SSLContext | None = None,
    ) -> None:
        """Create a proxy; see the class docstring for the arguments. Call `start` to listen."""
        if not secret:
            msg = "a proxy secret is required"
            raise ValueError(msg)
        self._token: Token = token
        self._secret: bytes = secret.encode()
        self._max_body_size: int = max_body_size
        self._ssl: SSLContext | None = ssl
        self._host: str = host
        self._port: int = port
        self._path: str = path.rstrip("/")
        self._prefix: re.Pattern[str] = re.compile(
            re.escape(self._path) + r"/v(?P<version>[0-9]+)(?P<rest>/.*)"
        )
        self._metrics: Metrics = metrics or NoopMetrics()
        self._rate_limiter: RateLimiter = rate_limiter or LocalRateLimiter(metrics=self._metrics)
        self._transport: HTTPTransport = transport or AiohttpTransport()
        self._base_url: str = base_url.rstrip("/")
        self._max_rate_limit_wait: float = max_rate_limit_wait
        self._routes: RouteTable = RouteTable()
        self._token_invalid: bool = False
        self._runner: web.AppRunner | None = None
        self._start_lock: asyncio.Lock = asyncio.Lock()

    @property
    def address(self) -> tuple[str, int]:
        """The host and port the proxy listens on.

        Raises:
            RuntimeError: The proxy has not been started.
        """
        addresses = self._runner.addresses if self._runner is not None else []
        if not addresses:
            msg = "the proxy is not listening"
            raise RuntimeError(msg)
        host, port = addresses[0][:2]
        return str(host), int(port)

    def install(self, app: web.Application) -> None:
        """Add the proxy's route to an existing aiohttp application."""
        app.router.add_route("*", self._path + "/{tail:.*}", self.handle)

    async def start(self) -> None:
        """Start listening. Idempotent, and safe to call concurrently.

        Raises:
            OSError: The address could not be bound, such as a port already in use.
        """
        async with self._start_lock:
            if self._runner is not None:
                return
            app = web.Application(client_max_size=self._max_body_size)
            self.install(app)
            runner = web.AppRunner(app, access_log=None)
            await runner.setup()
            try:
                await web.TCPSite(runner, self._host, self._port, ssl_context=self._ssl).start()
            except BaseException:
                await runner.cleanup()
                raise
            self._runner = runner
        _log.info("REST proxy listening on %s:%d%s", *self.address, self._path)

    async def close(self) -> None:
        """Stop listening and close the transport. Idempotent."""
        runner, self._runner = self._runner, None
        if runner is not None:
            try:
                await runner.cleanup()
            finally:
                await self._transport.close()

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def handle(self, request: web.Request) -> web.Response:
        """Send one request to Discord and answer with Discord's response."""
        given = request.headers.get(PROXY_SECRET_HEADER, "").encode()
        if not hmac.compare_digest(given, self._secret):
            return _error(HTTPStatus.UNAUTHORIZED, "the proxy's secret is required")
        target = self._prefix.fullmatch(request.raw_path.partition("?")[0])
        route = None if target is None else self._routes.match(request.method, target["rest"])
        if target is None or route is None:
            return _error(HTTPStatus.NOT_FOUND, "no Discord route has this method and path")
        authorize = not route.route.token_authenticated
        if authorize and self._token_invalid:
            return _error(HTTPStatus.UNAUTHORIZED, "Discord rejected the proxy's token")
        body = await request.read()
        headers = {name: value for name, value in request.headers.items() if name.lower() in _FORWARDED}
        if authorize:
            headers["Authorization"] = self._token.header
        url = f"{self._base_url}/v{target['version']}{route.path}"
        query = request.rel_url.raw_query_string  # as sent: the decoded one loses `%26` and `%23`
        if query:
            url = f"{url}?{query}"
        try:
            await self._rate_limiter.acquire(route, max_wait=self._max_rate_limit_wait)
        except WaitTooLongError as error:
            self._metrics.increment(REST_RATE_LIMITED, {"route": route.route.key, "scope": "proxy"})
            _log.info(
                "%s %s held %.2fs by the proxy's rate limits; answering 429",
                route.method,
                route.display,
                error.seconds,
            )
            return _held(error.seconds)
        try:
            response = await self._transport.request(route.method, url, headers=headers, body=body or None)
        except OSError:
            self._rate_limiter.release(route, None, None, None)
            _log.warning("%s %s failed at the network level", route.method, route.display)
            return _error(HTTPStatus.BAD_GATEWAY, "Discord could not be reached")
        except BaseException:
            self._rate_limiter.release(route, None, None, None)
            raise
        limits, retry_after = rate_limit_of(response.status, response.headers, response.body)
        self._rate_limiter.release(route, response.status, limits, retry_after)
        self._metrics.increment(
            REST_REQUESTS,
            {"method": route.method.value, "route": route.route.key, "status": str(response.status)},
        )
        if response.status == HTTPStatus.UNAUTHORIZED and authorize and self._token.type is TokenType.BOT:
            self._token_invalid = True
            _log.error("bot token rejected (401); refusing further requests to avoid an IP ban")
        return web.Response(
            status=response.status,
            body=response.body,
            headers={name: value for name, value in response.headers.items() if name not in _NOT_RETURNED},
        )


def _error(status: HTTPStatus, message: str) -> web.Response:
    return web.Response(status=status, body=encode_json({"message": message, "code": 0}), content_type=_JSON)


def _held(seconds: float) -> web.Response:
    """A 429 for a request the limiter would hold too long, in the shape Discord sends one."""
    return web.Response(
        status=HTTPStatus.TOO_MANY_REQUESTS,
        body=encode_json(
            {"message": "held by the proxy's rate limits", "retry_after": seconds, "global": False}
        ),
        content_type=_JSON,
        headers={"Retry-After": f"{seconds:.3f}", "X-RateLimit-Scope": "shared"},
    )
