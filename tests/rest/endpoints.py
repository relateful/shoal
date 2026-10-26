from shoal.payloads.api import DOCS_BASE_URL
from shoal.rest import endpoints
from tests.rest.resources import (
    application_commands,
    channel,
    emoji,
    gateway,
    guild,
    interactions,
    invite,
    message,
    soundboard,
    sticker,
    user,
    voice,
    webhook,
)
from tests.support.rest import EndpointCase, check_endpoint

ALL_CASES: list[EndpointCase] = [
    *application_commands.CASES,
    *channel.CASES,
    *emoji.CASES,
    *gateway.CASES,
    *guild.CASES,
    *interactions.CASES,
    *invite.CASES,
    *message.CASES,
    *soundboard.CASES,
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
