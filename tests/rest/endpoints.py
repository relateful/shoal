import inspect

from shoal.payloads.api import DOCS_BASE_URL
from shoal.rest import endpoints, resources
from shoal.rest.client import RestClient
from shoal.rest.requester import Resource
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
from tests.support.fakes import FakeTransport
from tests.support.rest import EndpointCase, check_endpoint, endpoint_methods, make_client

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
    checked = 0
    for name, method in endpoint_methods():
        if "reason" in inspect.signature(method).parameters:
            checked += 1
            assert "reason=reason" in inspect.getsource(method), f"{name} takes reason but does not send it"
    assert checked > 0


def test_every_resource_is_reached_from_the_client() -> None:
    client = make_client(FakeTransport())
    wired = {
        type(value).__name__: name
        for name in RestClient.__slots__
        if isinstance(value := getattr(client, name, None), Resource)
    }
    assert sorted(wired) == sorted(resources.__all__)
    for class_name, attribute in wired.items():
        # One spelling: `Messages` is `rest.messages`, `ScheduledEvents` is `rest.scheduled_events`.
        assert attribute.replace("_", "") == class_name.lower(), class_name
