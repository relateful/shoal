import asyncio
import random

import pytest

from shoal.core.metrics import REST_RATE_LIMITED, REST_REQUESTS, REST_RETRIES, InMemoryMetrics
from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    CreateMessageParams,
    Guild,
    SearchGuildMessagesParams,
    SearchHasType,
    User,
    excluding,
)
from shoal.rest import endpoints
from shoal.rest.client import RestClient, Token, TokenType
from shoal.rest.defaults import DEFAULT_USER_AGENT
from shoal.rest.errors import (
    ClientClosedError,
    ForbiddenError,
    RateLimitedError,
    SearchIndexNotReadyError,
    ServerError,
    TokenInvalidatedError,
    UnauthorizedError,
)
from shoal.rest.ratelimit import LocalRateLimiter
from tests.support.fakes import FakeClock, FakeTransport

USER: dict[str, object] = {
    "id": "1",
    "username": "bot",
    "discriminator": "0",
    "global_name": None,
    "avatar": None,
}
GUILD: dict[str, object] = {
    "id": "2",
    "name": "g",
    "owner_id": "1",
    "afk_timeout": 0,
    "roles": [],
    "emojis": [],
    "features": [],
    "preferred_locale": "en-US",
    "premium_progress_bar_enabled": False,
    **dict.fromkeys(
        (
            "icon",
            "splash",
            "discovery_splash",
            "afk_channel_id",
            "application_id",
            "system_channel_id",
            "rules_channel_id",
            "vanity_url_code",
            "description",
            "banner",
            "public_updates_channel_id",
            "safety_alerts_channel_id",
        )
    ),
    **dict.fromkeys(
        (
            "verification_level",
            "default_message_notifications",
            "explicit_content_filter",
            "mfa_level",
            "system_channel_flags",
            "premium_tier",
            "nsfw_level",
        ),
        0,
    ),
}
MESSAGE: dict[str, object] = {
    "id": "9",
    "channel_id": "3",
    "author": USER,
    "content": "hi",
    "timestamp": "2024-01-01T00:00:00+00:00",
    "edited_timestamp": None,
    "tts": False,
    "mention_everyone": False,
    "mentions": [],
    "mention_roles": [],
    "attachments": [],
    "embeds": [],
    "pinned": False,
    "type": 0,
}


def make_client(
    transport: FakeTransport, *, token: Token | None = None, metrics: InMemoryMetrics | None = None
) -> RestClient:
    clock = FakeClock()
    return RestClient(
        token or Token.bot("secret"),
        transport=transport,
        rate_limiter=LocalRateLimiter(clock=clock, global_per_second=None),
        clock=clock,
        metrics=metrics,
        random_source=random.Random(0),
    )


def test_tokens_build_headers_and_hide_secrets() -> None:
    bot = Token.bot("Bot abc")
    assert bot.header == "Bot abc"
    assert Token.bearer("Bearer xyz").header == "Bearer xyz"
    assert bot.type is TokenType.BOT
    assert "abc" not in repr(bot)


async def test_successful_request_decodes_and_sends_required_headers() -> None:
    transport = FakeTransport()
    transport.queue(200, USER)
    metrics = InMemoryMetrics()
    async with make_client(transport, metrics=metrics) as client:
        user = await client.get_current_user()
    assert isinstance(user, User)
    assert user.id == 1
    assert user.username == "bot"
    request = transport.requests[0]
    assert request.method == "GET"
    assert request.url == "https://discord.com/api/v10/users/@me"
    assert request.headers["Authorization"] == "Bot secret"
    assert request.headers["User-Agent"] == DEFAULT_USER_AGENT
    assert transport.closed
    key = InMemoryMetrics.key(REST_REQUESTS, {"method": "GET", "route": "GET /users/@me", "status": "200"})
    assert metrics.counters[key] == 1


async def test_query_booleans_body_and_audit_reason() -> None:
    transport = FakeTransport()
    transport.queue(200, GUILD)
    transport.queue(204)
    client = make_client(transport)
    result = await client.get_guild(2, with_counts=True)
    assert isinstance(result, Guild)
    await client.delete_message(3, 4, reason="spam & abuse")
    assert transport.requests[0].url.endswith("/guilds/2?with_counts=true")
    assert transport.requests[1].headers["X-Audit-Log-Reason"] == "spam %26 abuse"


async def test_json_body_is_encoded_with_content_type() -> None:
    transport = FakeTransport()
    transport.queue(200, MESSAGE)
    sent = await make_client(transport).create_message(3, CreateMessageParams(content="hi"))
    assert sent.content == "hi"
    request = transport.requests[0]
    assert request.headers["Content-Type"] == "application/json"
    assert request.body == b'{"content":"hi"}'


async def test_rate_limited_requests_are_retried() -> None:
    transport = FakeTransport()
    transport.queue(
        429, {"message": "slow", "retry_after": 0.5, "global": False}, {"x-ratelimit-scope": "user"}
    )
    transport.queue(200, USER)
    metrics = InMemoryMetrics()
    user = await make_client(transport, metrics=metrics).get_user(1)
    assert user.id == 1
    assert len(transport.requests) == 2
    assert (
        metrics.counters[
            InMemoryMetrics.key(REST_RATE_LIMITED, {"route": "GET /users/{user_id}", "scope": "user"})
        ]
        == 1
    )
    assert (
        metrics.counters[
            InMemoryMetrics.key(REST_RETRIES, {"route": "GET /users/{user_id}", "reason": "rate_limited"})
        ]
        == 1
    )


async def test_long_rate_limits_raise_instead_of_waiting() -> None:
    transport = FakeTransport()
    transport.queue(429, {"message": "slow", "retry_after": 3600, "global": False})
    with pytest.raises(RateLimitedError):
        await make_client(transport).get_user(1)


async def test_idempotent_requests_retry_server_errors_but_posts_do_not() -> None:
    transport = FakeTransport()
    transport.queue(502)
    transport.queue(200, USER)
    assert (await make_client(transport).get_user(1)).id == 1

    transport = FakeTransport()
    transport.queue(502)
    with pytest.raises(ServerError):
        await make_client(transport).create_message(1, CreateMessageParams(content="x"))
    assert len(transport.requests) == 1


async def test_network_errors_retry_then_raise() -> None:
    transport = FakeTransport()
    for _ in range(4):
        transport.queue_error(ConnectionResetError("reset"))
    with pytest.raises(ConnectionResetError):
        await make_client(transport).get_user(1)
    assert len(transport.requests) == 4


async def test_a_cancelled_request_does_not_block_its_route() -> None:
    transport = FakeTransport()
    client = make_client(transport)
    first = asyncio.create_task(client.get_user(1))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    transport.queue(200, USER)
    user = await asyncio.wait_for(client.get_user(1), timeout=1)
    assert user.username == "bot"


async def test_bot_401_stops_all_further_requests() -> None:
    transport = FakeTransport()
    transport.queue(401, {"code": 0, "message": "401: Unauthorized"})
    client = make_client(transport)
    with pytest.raises(UnauthorizedError):
        await client.get_current_user()
    with pytest.raises(TokenInvalidatedError):
        await client.get_current_user()
    assert len(transport.requests) == 1


async def test_bearer_401_does_not_lock_the_client() -> None:
    transport = FakeTransport()
    transport.queue(401, {"code": 0, "message": "401: Unauthorized"})
    transport.queue(200, USER)
    client = make_client(transport, token=Token.bearer("user-token"))
    with pytest.raises(UnauthorizedError):
        await client.get_current_user()
    assert (await client.get_current_user()).id == 1


async def test_errors_carry_discord_codes() -> None:
    transport = FakeTransport()
    transport.queue(403, {"code": 50013, "message": "Missing Permissions"})
    with pytest.raises(ForbiddenError) as caught:
        await make_client(transport).get_channel(5)
    assert caught.value.code == 50013


async def test_closed_client_refuses_requests() -> None:
    client = make_client(FakeTransport())
    await client.close()
    with pytest.raises(ClientClosedError):
        await client.get_current_user()


def test_rejects_negative_retries() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        RestClient(None, transport=FakeTransport(), max_retries=-1)


def test_base_url_points_at_a_proxy() -> None:
    client = RestClient(None, transport=FakeTransport(), base_url="http://rest-proxy:8080/api/")
    assert client.base_url == "http://rest-proxy:8080/api/v10"
    assert endpoints.GET_GATEWAY.compile().path == "/gateway"


async def test_search_sends_array_query_strings_and_flattens_matches() -> None:
    transport = FakeTransport()
    transport.queue(200, {"doing_deep_historical_index": False, "total_results": 1, "messages": [[MESSAGE]]})
    params = SearchGuildMessagesParams(
        content="hi there",
        channel_id=[Snowflake(1), Snowflake(2)],
        has=[SearchHasType.IMAGE, excluding(SearchHasType.LINK)],
        pinned=False,
    )
    result = await make_client(transport).search_guild_messages(5, params)
    assert [message.id for message in result.matches] == [9]
    assert transport.requests[0].url.endswith(
        "/guilds/5/messages/search?content=hi+there&channel_id=1&channel_id=2&pinned=false&has=image&has=-link"
    )


async def test_search_waits_while_the_guild_is_being_indexed() -> None:
    transport = FakeTransport()
    pending = {"message": "Index not yet available", "code": 110000, "documents_indexed": 0, "retry_after": 2}
    transport.queue(202, pending)
    transport.queue(202, pending | {"retry_after": 0})
    transport.queue(200, {"doing_deep_historical_index": True, "total_results": 0, "messages": []})
    client = make_client(transport)
    result = await client.search_guild_messages(5, SearchGuildMessagesParams())
    assert result.total_results == 0
    assert len(transport.requests) == 3


async def test_search_gives_up_with_a_typed_error() -> None:
    transport = FakeTransport()
    pending = {
        "message": "Index not yet available",
        "code": 110000,
        "documents_indexed": 40,
        "retry_after": 1,
    }
    for _ in range(4):
        transport.queue(202, pending)
    with pytest.raises(SearchIndexNotReadyError) as caught:
        await make_client(transport).search_guild_messages(5, SearchGuildMessagesParams())
    assert caught.value.documents_indexed == 40
