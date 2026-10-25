import asyncio
import random
from collections.abc import Awaitable, Callable

import msgspec
import pytest

from shoal.core.codec import encode_json
from shoal.core.metrics import REST_RATE_LIMITED, REST_REQUESTS, REST_RETRIES, InMemoryMetrics
from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    ApplicationCommandPermission,
    ApplicationCommandPermissionType,
    BulkApplicationCommandParams,
    CreateFollowupMessageParams,
    CreateGlobalApplicationCommandParams,
    CreateGuildApplicationCommandParams,
    CreateMessageParams,
    DeferredMessageResponse,
    EditApplicationCommandPermissionsParams,
    EditGlobalApplicationCommandParams,
    EditGuildApplicationCommandParams,
    EditWebhookMessageParams,
    Guild,
    InteractionMessage,
    MessageResponse,
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
    NotFoundError,
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


COMMAND: dict[str, object] = {
    "id": "5",
    "application_id": "7",
    "name": "ping",
    "description": "Check the bot",
    "default_member_permissions": None,
    "version": "1",
}
PERMISSIONS: dict[str, object] = {
    "id": "5",
    "application_id": "7",
    "guild_id": "2",
    "permissions": [{"id": "2", "type": 1, "permission": True}],
}
GLOBAL_COMMANDS = "https://discord.com/api/v10/applications/7/commands"
GUILD_COMMANDS = "https://discord.com/api/v10/applications/7/guilds/2/commands"

type CommandCall = Callable[[RestClient], Awaitable[object]]

COMMAND_CALLS: list[tuple[str, CommandCall, str, str, object, object]] = [
    (
        "get global",
        lambda client: client.get_global_application_commands(7),
        "GET",
        f"{GLOBAL_COMMANDS}?with_localizations=false",
        None,
        [COMMAND],
    ),
    (
        "create global",
        lambda client: client.create_global_application_command(
            7, CreateGlobalApplicationCommandParams(name="ping", description="Check the bot")
        ),
        "POST",
        GLOBAL_COMMANDS,
        {"name": "ping", "description": "Check the bot"},
        COMMAND,
    ),
    (
        "get one global",
        lambda client: client.get_global_application_command(7, 5),
        "GET",
        f"{GLOBAL_COMMANDS}/5",
        None,
        COMMAND,
    ),
    (
        "edit global",
        lambda client: client.edit_global_application_command(
            7, 5, EditGlobalApplicationCommandParams(nsfw=True)
        ),
        "PATCH",
        f"{GLOBAL_COMMANDS}/5",
        {"nsfw": True},
        COMMAND,
    ),
    (
        "delete global",
        lambda client: client.delete_global_application_command(7, 5),
        "DELETE",
        f"{GLOBAL_COMMANDS}/5",
        None,
        None,
    ),
    (
        "bulk global",
        lambda client: client.bulk_overwrite_global_application_commands(7, []),
        "PUT",
        GLOBAL_COMMANDS,
        [],
        [],
    ),
    (
        "get guild",
        lambda client: client.get_guild_application_commands(7, 2, with_localizations=True),
        "GET",
        f"{GUILD_COMMANDS}?with_localizations=true",
        None,
        [COMMAND],
    ),
    (
        "create guild",
        lambda client: client.create_guild_application_command(
            7, 2, CreateGuildApplicationCommandParams(name="ping", description="Check the bot")
        ),
        "POST",
        GUILD_COMMANDS,
        {"name": "ping", "description": "Check the bot"},
        COMMAND,
    ),
    (
        "get one guild",
        lambda client: client.get_guild_application_command(7, 2, 5),
        "GET",
        f"{GUILD_COMMANDS}/5",
        None,
        COMMAND,
    ),
    (
        "edit guild",
        lambda client: client.edit_guild_application_command(
            7, 2, 5, EditGuildApplicationCommandParams(name="pong")
        ),
        "PATCH",
        f"{GUILD_COMMANDS}/5",
        {"name": "pong"},
        COMMAND,
    ),
    (
        "delete guild",
        lambda client: client.delete_guild_application_command(7, 2, 5),
        "DELETE",
        f"{GUILD_COMMANDS}/5",
        None,
        None,
    ),
    (
        "bulk guild",
        lambda client: client.bulk_overwrite_guild_application_commands(
            7, 2, [BulkApplicationCommandParams(name="ping", description="Check the bot")]
        ),
        "PUT",
        GUILD_COMMANDS,
        [{"name": "ping", "description": "Check the bot"}],
        [COMMAND],
    ),
    (
        "guild permissions",
        lambda client: client.get_guild_application_command_permissions(7, 2),
        "GET",
        f"{GUILD_COMMANDS}/permissions",
        None,
        [PERMISSIONS],
    ),
    (
        "command permissions",
        lambda client: client.get_application_command_permissions(7, 2, 5),
        "GET",
        f"{GUILD_COMMANDS}/5/permissions",
        None,
        PERMISSIONS,
    ),
    (
        "edit permissions",
        lambda client: client.edit_application_command_permissions(
            7,
            2,
            5,
            EditApplicationCommandPermissionsParams(
                permissions=[
                    ApplicationCommandPermission(
                        id=Snowflake(2), type=ApplicationCommandPermissionType.ROLE, permission=True
                    )
                ]
            ),
        ),
        "PUT",
        f"{GUILD_COMMANDS}/5/permissions",
        {"permissions": [{"id": "2", "type": 1, "permission": True}]},
        PERMISSIONS,
    ),
]


@pytest.mark.parametrize(
    ("call", "method", "url", "body", "response"),
    [case[1:] for case in COMMAND_CALLS],
    ids=[case[0] for case in COMMAND_CALLS],
)
async def test_application_command_endpoints(
    call: CommandCall, method: str, url: str, body: object, response: object
) -> None:
    transport = FakeTransport()
    transport.queue(204 if response is None else 200, response)
    client = make_client(transport)
    result = await call(client)
    request = transport.requests[0]
    assert (request.method, request.url) == (method, url)
    assert (msgspec.json.decode(request.body) if request.body is not None else None) == body
    if response is None:
        assert result is None
    else:
        # Re-encoding what the client returned gives back what Discord sent: nothing lost or mistyped.
        # The one allowed difference: UTC times come back as `Z` rather than Discord's `+00:00`.
        sent = msgspec.json.encode(response).replace(b"+00:00", b"Z")
        assert msgspec.json.decode(encode_json(result)) == msgspec.json.decode(sent)


INTERACTION_WEBHOOK = "https://discord.com/api/v10/webhooks/7/aW50ZXJhY3Rpb24"

INTERACTION_CALLS: list[tuple[str, CommandCall, str, str, object, object]] = [
    (
        "respond",
        lambda client: client.create_interaction_response(
            9, "aW50ZXJhY3Rpb24", MessageResponse(data=InteractionMessage(content="hi"))
        ),
        "POST",
        "https://discord.com/api/v10/interactions/9/aW50ZXJhY3Rpb24/callback",
        {"type": 4, "data": {"content": "hi"}},
        None,
    ),
    (
        "respond with response",
        lambda client: client.create_interaction_response(
            9, "aW50ZXJhY3Rpb24", DeferredMessageResponse(), with_response=True
        ),
        "POST",
        "https://discord.com/api/v10/interactions/9/aW50ZXJhY3Rpb24/callback?with_response=true",
        {"type": 5},
        {"interaction": {"id": "9", "type": 2}},
    ),
    (
        "get original",
        lambda client: client.get_original_interaction_response(7, "aW50ZXJhY3Rpb24"),
        "GET",
        f"{INTERACTION_WEBHOOK}/messages/@original",
        None,
        MESSAGE,
    ),
    (
        "edit original",
        lambda client: client.edit_original_interaction_response(
            7, "aW50ZXJhY3Rpb24", EditWebhookMessageParams(content=None)
        ),
        "PATCH",
        f"{INTERACTION_WEBHOOK}/messages/@original",
        {"content": None},
        MESSAGE,
    ),
    (
        "delete original",
        lambda client: client.delete_original_interaction_response(7, "aW50ZXJhY3Rpb24"),
        "DELETE",
        f"{INTERACTION_WEBHOOK}/messages/@original",
        None,
        None,
    ),
    (
        "follow up",
        lambda client: client.create_followup_message(
            7, "aW50ZXJhY3Rpb24", CreateFollowupMessageParams(content="later")
        ),
        "POST",
        INTERACTION_WEBHOOK,
        {"content": "later"},
        MESSAGE,
    ),
    (
        "get follow-up",
        lambda client: client.get_followup_message(7, "aW50ZXJhY3Rpb24", 9),
        "GET",
        f"{INTERACTION_WEBHOOK}/messages/9",
        None,
        MESSAGE,
    ),
    (
        "edit follow-up",
        lambda client: client.edit_followup_message(
            7, "aW50ZXJhY3Rpb24", 9, EditWebhookMessageParams(content="edited")
        ),
        "PATCH",
        f"{INTERACTION_WEBHOOK}/messages/9",
        {"content": "edited"},
        MESSAGE,
    ),
    (
        "delete follow-up",
        lambda client: client.delete_followup_message(7, "aW50ZXJhY3Rpb24", 9),
        "DELETE",
        f"{INTERACTION_WEBHOOK}/messages/9",
        None,
        None,
    ),
]


@pytest.mark.parametrize(
    ("call", "method", "url", "body", "response"),
    [case[1:] for case in INTERACTION_CALLS],
    ids=[case[0] for case in INTERACTION_CALLS],
)
async def test_interaction_endpoints(
    call: CommandCall, method: str, url: str, body: object, response: object
) -> None:
    await test_application_command_endpoints(call, method, url, body, response)


async def test_interaction_tokens_stay_out_of_errors() -> None:
    transport = FakeTransport()
    transport.queue(404, {"message": "Unknown Webhook", "code": 10015})
    client = make_client(transport)
    with pytest.raises(NotFoundError) as caught:
        await client.get_original_interaction_response(7, "aW50ZXJhY3Rpb24")
    assert "aW50ZXJhY3Rpb24" not in str(caught.value)
    assert "{interaction_token}" in str(caught.value)
