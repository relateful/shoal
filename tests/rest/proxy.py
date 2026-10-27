import asyncio
import contextlib
from collections.abc import Mapping
from typing import override

import aiohttp
import msgspec
import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from shoal.core.codec import JSONObject, encode_json
from shoal.core.metrics import REST_RATE_LIMITED, REST_REQUESTS, InMemoryMetrics, Metrics
from shoal.payloads.api import API_VERSION
from shoal.rest import RestClient, Token, endpoints
from shoal.rest.defaults import PROXY_SECRET_HEADER
from shoal.rest.errors import RateLimitedError
from shoal.rest.proxy import RestProxy, RouteTable
from shoal.rest.ratelimit import LocalRateLimiter
from shoal.rest.transport import HTTPResponse, HTTPTransport
from tests.support.fakes import FakeClock, FakeTransport, settle

USER: JSONObject = {"id": "3", "username": "u", "discriminator": "0", "global_name": None, "avatar": None}
TOKEN = Token.bot("bot-token")
SECRET = "proxy-secret"
DISCORD = "https://discord.test/api"


def proxy_of(discord: FakeTransport, *, max_wait: float = 60.0, metrics: Metrics | None = None) -> RestProxy:
    return RestProxy(
        TOKEN,
        secret=SECRET,
        port=0,
        transport=discord,
        rate_limiter=LocalRateLimiter(clock=FakeClock(), global_per_second=None),
        base_url=DISCORD,
        max_rate_limit_wait=max_wait,
        metrics=metrics,
    )


def base_of(proxy: RestProxy) -> str:
    host, port = proxy.address
    return f"http://{host}:{port}/api"


async def send(
    proxy: RestProxy, method: str, path: str, *, secret: str | None = SECRET, body: bytes = b""
) -> tuple[int, dict[str, str], bytes]:
    headers = {} if secret is None else {PROXY_SECRET_HEADER: secret}
    async with (
        aiohttp.ClientSession() as session,
        session.request(
            method, f"{base_of(proxy)}/v{API_VERSION}{path}", headers=headers, data=body
        ) as response,
    ):
        return response.status, dict(response.headers), await response.read()


async def test_a_client_with_only_the_secret_reaches_discord_with_the_bot_token() -> None:
    discord = FakeTransport()
    discord.queue(200, USER, {"x-ratelimit-bucket": "users", "content-type": "application/json"})
    metrics = InMemoryMetrics()
    async with proxy_of(discord, metrics=metrics) as proxy:
        rest = RestClient(None, base_url=base_of(proxy), proxy_secret=SECRET)
        try:
            user = await rest.users.get(3)
        finally:
            await rest.close()
    assert user.username == "u"
    (sent,) = discord.requests
    assert (sent.method, sent.url) == ("GET", f"{DISCORD}/v{API_VERSION}/users/3")
    assert sent.headers["Authorization"] == TOKEN.header
    assert sent.headers["User-Agent"].startswith("DiscordBot")
    assert PROXY_SECRET_HEADER not in sent.headers
    labels = {"method": "GET", "route": "GET /users/{user_id}", "status": "200"}
    assert metrics.counters[InMemoryMetrics.key(REST_REQUESTS, labels)] == 1


async def test_bodies_queries_and_reasons_are_passed_on() -> None:
    discord = FakeTransport()
    discord.queue(204)
    async with (
        proxy_of(discord) as proxy,
        aiohttp.ClientSession() as session,
        session.put(
            f"{base_of(proxy)}/v{API_VERSION}/guilds/1/bans/2?x=a%26b%23c&y=%20",
            headers={
                PROXY_SECRET_HEADER: SECRET,
                "Authorization": "Bot someone-else",
                "Content-Type": "application/json",
                "X-Audit-Log-Reason": "spam",
                "Cookie": "not passed on",
            },
            data=b'{"delete_message_seconds":0}',
        ) as response,
    ):
        assert response.status == 204
    (sent,) = discord.requests
    # The query reaches Discord exactly as sent: decoding it would turn `%23` into a fragment.
    assert sent.url == f"{DISCORD}/v{API_VERSION}/guilds/1/bans/2?x=a%26b%23c&y=%20"
    assert sent.headers["Authorization"] == TOKEN.header  # the caller's own is never passed on
    assert sent.body == b'{"delete_message_seconds":0}'
    assert sent.headers["X-Audit-Log-Reason"] == "spam"
    assert "Cookie" not in sent.headers


async def test_every_request_needs_the_proxys_secret() -> None:
    discord = FakeTransport()
    async with proxy_of(discord) as proxy:
        assert (await send(proxy, "GET", "/users/3", secret=None))[0] == 401
        assert (await send(proxy, "GET", "/users/3", secret="wrong"))[0] == 401
        # Token routes too: otherwise anyone reaching the port could spend the invalid request budget.
        assert (await send(proxy, "POST", "/webhooks/1/hook-token", secret=None))[0] == 401
    assert discord.requests == []
    with pytest.raises(ValueError, match="secret is required"):
        RestProxy(TOKEN, secret="")


async def test_a_token_in_the_path_needs_no_bot_token_and_cookies_stay_behind() -> None:
    discord = FakeTransport()
    discord.queue(204, None, {"set-cookie": "__cf_bm=abc", "x-ratelimit-bucket": "hooks"})
    async with proxy_of(discord) as proxy:
        status, headers, _ = await send(proxy, "POST", "/webhooks/1/hook-token", body=b"{}")
    assert status == 204
    assert "Set-Cookie" not in headers
    assert headers["x-ratelimit-bucket"] == "hooks"
    (sent,) = discord.requests
    assert "Authorization" not in sent.headers


async def test_a_path_with_no_discord_route_is_refused() -> None:
    discord = FakeTransport()
    async with proxy_of(discord) as proxy:
        status, _, body = await send(proxy, "GET", "/nothing/here")
        assert status == 404
        assert msgspec.json.decode(body)["code"] == 0
        assert (await send(proxy, "GET", "/channels/1/messages/.."))[0] == 404
        async with (
            aiohttp.ClientSession() as session,
            session.get(f"{base_of(proxy)}/users/3", headers={PROXY_SECRET_HEADER: SECRET}) as response,
        ):
            assert response.status == 404  # no version
    assert discord.requests == []


async def test_a_request_held_too_long_is_answered_with_a_shared_429() -> None:
    discord = FakeTransport()
    discord.queue(
        200,
        USER,
        {
            "x-ratelimit-bucket": "users",
            "x-ratelimit-limit": "1",
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset-after": "30",
        },
    )
    metrics = InMemoryMetrics()
    async with proxy_of(discord, max_wait=5.0, metrics=metrics) as proxy:
        assert (await send(proxy, "GET", "/users/3"))[0] == 200
        status, headers, body = await send(proxy, "GET", "/users/4")
        assert status == 429
        assert headers["X-RateLimit-Scope"] == "shared"
        assert 29.0 < msgspec.json.decode(body)["retry_after"] <= 30.0
        held = InMemoryMetrics.key(REST_RATE_LIMITED, {"route": "GET /users/{user_id}", "scope": "proxy"})
        assert metrics.counters[held] == 1
        limiter = LocalRateLimiter()
        rest = RestClient(
            None, base_url=base_of(proxy), proxy_secret=SECRET, rate_limiter=limiter, max_rate_limit_wait=5.0
        )
        try:
            with pytest.raises(RateLimitedError):
                await rest.users.get(5)
            assert limiter.invalid_guard.count == 0  # a shared 429 is not an invalid request
        finally:
            await rest.close()
    assert len(discord.requests) == 1


async def test_a_network_failure_is_a_502_and_frees_the_route() -> None:
    discord = FakeTransport()
    discord.queue_error(ConnectionResetError())
    discord.queue(200, USER)
    async with proxy_of(discord) as proxy:
        assert (await send(proxy, "GET", "/users/3"))[0] == 502
        assert (await send(proxy, "GET", "/users/3"))[0] == 200


async def test_a_rejected_bot_token_stops_every_bot_request() -> None:
    discord = FakeTransport()
    discord.queue(401, {"message": "401: Unauthorized", "code": 0})
    discord.queue(204)
    async with proxy_of(discord) as proxy:
        assert (await send(proxy, "GET", "/users/3"))[0] == 401
        status, _, body = await send(proxy, "GET", "/users/3")
        assert status == 401
        assert b"rejected" in body
        assert (await send(proxy, "POST", "/webhooks/1/hook-token"))[0] == 204
    assert len(discord.requests) == 2


async def test_starting_and_closing_are_idempotent() -> None:
    discord = FakeTransport()
    proxy = proxy_of(discord)
    with pytest.raises(RuntimeError, match="not listening"):
        _ = proxy.address
    await proxy.start()
    await proxy.start()
    await proxy.close()
    await proxy.close()
    assert discord.closed


def test_routes_are_found_from_their_paths() -> None:
    table = RouteTable()
    me = table.match("GET", "/users/@me")
    assert me is not None
    assert me.route is endpoints.GET_CURRENT_USER
    webhook = table.match("POST", "/webhooks/1/a%2Fb")
    assert webhook is not None
    # A webhook's path and an interaction follow-up's have one shape: the global limit counts it.
    assert webhook.route is endpoints.EXECUTE_WEBHOOK
    assert webhook.path == "/webhooks/1/a%2Fb"
    assert table.match("TRACE", "/users/@me") is None
    assert table.match("GET", "/channels/1/messages/..") is None  # would name the channel's messages
    only = RouteTable([endpoints.GET_USER])
    assert only.match("GET", "/users/@me") is not None
    assert only.match("GET", "/guilds/1") is None


async def test_a_port_in_use_leaves_nothing_half_started() -> None:
    discord = FakeTransport()
    async with proxy_of(discord) as running:
        _, port = running.address
        taken = RestProxy(TOKEN, secret=SECRET, port=port, transport=discord)
        with pytest.raises(OSError):  # noqa: PT011 - the platform decides which OSError
            await taken.start()
        with pytest.raises(RuntimeError, match="not listening"):
            _ = taken.address


async def test_a_request_cancelled_on_its_way_frees_the_route() -> None:
    class Stuck(HTTPTransport):
        def __init__(self) -> None:
            self.calls = 0

        @override
        async def request(
            self, method: str, url: str, *, headers: Mapping[str, str], body: bytes | None
        ) -> HTTPResponse:
            self.calls += 1
            if self.calls == 1:
                await asyncio.Event().wait()
            return HTTPResponse(200, {}, encode_json(USER))

        @override
        async def close(self) -> None:
            pass

    discord = Stuck()
    proxy = RestProxy(TOKEN, secret=SECRET, transport=discord, base_url=DISCORD)

    def request() -> web.Request:
        return make_mocked_request(
            "GET", f"/api/v{API_VERSION}/users/3", headers={PROXY_SECRET_HEADER: SECRET}
        )

    first = asyncio.ensure_future(proxy.handle(request()))
    await settle()
    assert discord.calls == 1
    first.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await first
    # The route's first request never answered; the next one is not held behind it.
    answer = await asyncio.wait_for(proxy.handle(request()), timeout=5)
    assert answer.status == 200
