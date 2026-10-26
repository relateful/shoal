import inspect

from shoal.payloads.api import DOCS_BASE_URL
from shoal.rest import endpoints
from shoal.rest.client import RestClient
from tests.rest.resources import (
    application,
    application_commands,
    application_identity,
    audit_log,
    auto_moderation,
    channel,
    emoji,
    gateway,
    guild,
    guild_template,
    interactions,
    invite,
    lobby,
    message,
    monetization,
    scheduled_event,
    soundboard,
    stage_instance,
    sticker,
    user,
    voice,
    webhook,
)
from tests.support.rest import EndpointCase, check_endpoint

ALL_CASES: list[EndpointCase] = [
    *application.CASES,
    *application_commands.CASES,
    *application_identity.CASES,
    *audit_log.CASES,
    *auto_moderation.CASES,
    *channel.CASES,
    *emoji.CASES,
    *gateway.CASES,
    *guild.CASES,
    *guild_template.CASES,
    *interactions.CASES,
    *invite.CASES,
    *lobby.CASES,
    *message.CASES,
    *monetization.CASES,
    *scheduled_event.CASES,
    *soundboard.CASES,
    *stage_instance.CASES,
    *sticker.CASES,
    *user.CASES,
    *voice.CASES,
    *webhook.CASES,
]


def test_every_declared_endpoint_links_to_its_docs_section() -> None:
    names = {name for name in dir(endpoints) if name.isupper() and name != "ALL_ROUTES"}
    declared = {getattr(endpoints, name) for name in names}
    assert declared == set(endpoints.ALL_ROUTES)
    for route in endpoints.ALL_ROUTES:
        assert route.docs.startswith(DOCS_BASE_URL)
        assert "#" in route.docs


def test_interaction_routes_skip_the_global_rate_limit() -> None:
    interaction_routes = [route for route in endpoints.ALL_ROUTES if "interaction_token" in route.parameters]
    assert len(interaction_routes) == 8
    assert not any(route.global_limit for route in interaction_routes)
    assert all(route.global_limit for route in endpoints.ALL_ROUTES if route not in interaction_routes)


async def test_every_endpoint_has_a_checked_call() -> None:
    # Search Guild Messages answers 202 while indexing, so tests/rest/client.py covers it on its own.
    covered = {endpoints.SEARCH_GUILD_MESSAGES.key}
    for case in ALL_CASES:
        covered.add(await check_endpoint(case))
    missing = sorted(route.key for route in endpoints.ALL_ROUTES if route.key not in covered)
    assert missing == [], "endpoints without a case in tests/rest/resources/"


def test_every_reason_reaches_the_request() -> None:
    # The endpoint cases check the header only where a case passes a reason; this covers the rest.
    for name, method in inspect.getmembers(RestClient, inspect.iscoroutinefunction):
        if name.startswith("_") or name in {"request", "request_empty", "request_optional"}:
            continue
        if "reason" in inspect.signature(method).parameters:
            source = inspect.getsource(method)
            assert "reason=reason" in source, f"RestClient.{name} takes reason but does not send it"
