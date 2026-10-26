import asyncio
import logging
from typing import override

import aiohttp
import msgspec
import pytest
from aiohttp import web

from shoal.core.clock import Clock
from shoal.core.codec import JSONObject
from shoal.core.metrics import (
    HTTP_INTERACTION_SECONDS,
    HTTP_INTERACTIONS,
    HTTP_WEBHOOK_EVENTS,
    InMemoryMetrics,
)
from shoal.endpoint import Endpoint
from shoal.payloads import (
    ApplicationCommandInteraction,
    Interaction,
    InteractionMessage,
    InteractionResponse,
    MessageResponse,
    UnknownInteraction,
    WebhookEventPayload,
    WebhookPayloadType,
)
from tests.support.endpoint import post, url_of
from tests.support.fakes import FakeClock, settle
from tests.support.server import free_port, serve
from tests.support.signing import PUBLIC

USER: JSONObject = {"id": "3", "username": "u", "discriminator": "0", "global_name": None, "avatar": None}
COMMAND: JSONObject = {
    "id": "10",
    "application_id": "11",
    "type": 2,
    "token": "aW50ZXJhY3Rpb24",
    "version": 1,
    "app_permissions": "0",
    "entitlements": [],
    "authorizing_integration_owners": {"1": "3"},
    "attachment_size_limit": 26214400,
    "user": USER,
    "data": {"id": "20", "name": "ping", "type": 1},
}
PING: JSONObject = {
    "id": "1",
    "application_id": "2",
    "type": 1,
    "token": "t",
    "version": 1,
    "user": USER,
    "app_permissions": "0",
    "authorizing_integration_owners": {},
    "entitlements": [],
}
"""A ping as Discord sends it, with more than the fields a ping needs."""
COMPONENT: JSONObject = {**COMMAND, "type": 3, "data": {"custom_id": "yes", "component_type": 2}}
AUTOCOMPLETE: JSONObject = {
    **COMMAND,
    "type": 4,
    "data": {
        "id": "20",
        "name": "card",
        "type": 1,
        "options": [{"type": 3, "name": "q", "value": "a", "focused": True}],
    },
}
MODAL_SUBMIT: JSONObject = {**COMMAND, "type": 5, "data": {"custom_id": "form", "components": []}}
MALFORMED: JSONObject = {"id": "1", "application_id": "2", "type": 2, "token": "t"}


class Recorder:
    """A handler that remembers what it received and answers with a fixed response."""

    def __init__(self, response: InteractionResponse | None) -> None:
        self.response = response
        self.received: list[Interaction | UnknownInteraction] = []

    async def __call__(self, interaction: Interaction | UnknownInteraction) -> InteractionResponse | None:
        self.received.append(interaction)
        return self.response


class SteppedClock(Clock):
    """A clock the test moves by hand, so a handler can take four seconds instantly."""

    def __init__(self) -> None:
        self.now = 0.0

    @override
    def monotonic(self) -> float:
        return self.now

    @override
    def wall(self) -> float:
        return self.now

    @override
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(0)


def counted(metrics: InMemoryMetrics, kind: str, result: str) -> float:
    return metrics.counters.get(InMemoryMetrics.key(HTTP_INTERACTIONS, {"type": kind, "result": result}), 0)


def timed(metrics: InMemoryMetrics, kind: str) -> list[float]:
    return metrics.observations.get(InMemoryMetrics.key(HTTP_INTERACTION_SECONDS, {"type": kind}), [])


async def test_ping_is_answered_without_the_handler() -> None:
    metrics = InMemoryMetrics()
    handler = Recorder(None)
    async with Endpoint(PUBLIC, handler, port=0, metrics=metrics) as server:
        status, body = await post(url_of(server), PING)
    assert (status, msgspec.json.decode(body)) == (200, {"type": 1})
    assert handler.received == []
    assert counted(metrics, "ping", "inline") == 1


async def test_requests_that_fail_the_signature_check_get_401() -> None:
    metrics = InMemoryMetrics()
    handler = Recorder(None)
    async with Endpoint(PUBLIC, handler, port=0, metrics=metrics) as server:
        forged, _ = await post(url_of(server), COMMAND, signature="00" * 64)
        unsigned, _ = await post(url_of(server), COMMAND, signature="")
        async with aiohttp.ClientSession() as session, session.post(url_of(server), json=COMMAND) as response:
            headerless = response.status
    assert (forged, unsigned, headerless) == (401, 401, 401)
    assert handler.received == []
    assert counted(metrics, "unknown", "invalid_signature") == 3


async def test_only_posts_to_the_path_are_served() -> None:
    async with (
        Endpoint(PUBLIC, Recorder(None), port=0) as server,
        aiohttp.ClientSession() as session,
    ):
        async with session.get(url_of(server)) as response:
            assert response.status == 405
        async with session.post(url_of(server).replace("/interactions", "/other"), data=b"{}") as response:
            assert response.status == 404


async def test_a_command_gets_the_handlers_response_inline() -> None:
    metrics = InMemoryMetrics()
    handler = Recorder(MessageResponse(data=InteractionMessage(content="pong")))
    async with Endpoint(PUBLIC, handler, port=0, metrics=metrics) as server:
        status, body = await post(url_of(server), COMMAND)
    assert status == 200
    assert msgspec.json.decode(body) == {"type": 4, "data": {"content": "pong"}}
    [interaction] = handler.received
    assert isinstance(interaction, ApplicationCommandInteraction)
    assert interaction.data.name == "ping"
    assert counted(metrics, "application_command", "inline") == 1


@pytest.mark.parametrize(
    ("payload", "label"),
    [
        (COMMAND, "application_command"),
        (COMPONENT, "message_component"),
        (AUTOCOMPLETE, "application_command_autocomplete"),
        (MODAL_SUBMIT, "modal_submit"),
        ({**PING, "type": 99}, "unknown"),
    ],
)
async def test_every_interaction_type_reaches_the_handler(payload: JSONObject, label: str) -> None:
    metrics = InMemoryMetrics()
    handler = Recorder(None)
    async with Endpoint(PUBLIC, handler, port=0, metrics=metrics) as server:
        status, body = await post(url_of(server), payload)
    assert (status, body) == (202, b"")
    assert len(handler.received) == 1
    assert counted(metrics, label, "callback") == 1
    assert len(timed(metrics, label)) == 1


async def test_newer_types_reach_the_handler_and_malformed_ones_do_not() -> None:
    metrics = InMemoryMetrics()
    handler = Recorder(None)
    async with Endpoint(PUBLIC, handler, port=0, metrics=metrics) as server:
        newer, _ = await post(url_of(server), {**PING, "type": 99})
        malformed, _ = await post(url_of(server), MALFORMED)
    assert (newer, malformed) == (202, 400)
    [interaction] = handler.received
    assert isinstance(interaction, UnknownInteraction)
    assert counted(metrics, "unknown", "malformed") == 1


async def test_a_failing_handler_is_logged_and_answered_500(caplog: pytest.LogCaptureFixture) -> None:
    async def explode(interaction: Interaction | UnknownInteraction) -> InteractionResponse | None:
        msg = f"broken for {interaction.id}"
        raise RuntimeError(msg)

    metrics = InMemoryMetrics()
    with caplog.at_level(logging.ERROR, logger="shoal.endpoint"):
        async with Endpoint(PUBLIC, explode, port=0, metrics=metrics) as server:
            status, _ = await post(url_of(server), COMMAND)
    assert status == 500
    assert "interaction handler failed for application_command interaction 10" in caplog.text
    assert counted(metrics, "application_command", "handler_error") == 1
    assert len(timed(metrics, "application_command")) == 1


async def test_a_hung_handler_is_given_up_on(caplog: pytest.LogCaptureFixture) -> None:
    async def hang(interaction: Interaction | UnknownInteraction) -> InteractionResponse | None:
        del interaction
        await asyncio.Event().wait()
        return None

    metrics = InMemoryMetrics()
    with caplog.at_level(logging.ERROR, logger="shoal.endpoint"):
        async with Endpoint(PUBLIC, hang, port=0, handler_timeout=0.05, metrics=metrics) as server:
            status, _ = await post(url_of(server), COMMAND)
    assert status == 500
    assert "did not finish within" in caplog.text
    assert counted(metrics, "application_command", "timeout") == 1


async def test_slow_handlers_are_warned_about(caplog: pytest.LogCaptureFixture) -> None:
    clock = SteppedClock()

    async def slow(interaction: Interaction | UnknownInteraction) -> InteractionResponse | None:
        del interaction
        clock.now += 4.0
        return None

    with caplog.at_level(logging.WARNING, logger="shoal.endpoint"):
        async with Endpoint(PUBLIC, slow, port=0, clock=clock) as server:
            status, _ = await post(url_of(server), COMMAND)
    assert status == 202
    assert "took 4.00s" in caplog.text


async def test_handlers_within_the_deadline_are_not_warned_about(caplog: pytest.LogCaptureFixture) -> None:
    clock = SteppedClock()

    async def on_time(interaction: Interaction | UnknownInteraction) -> InteractionResponse | None:
        del interaction
        clock.now += 3.0
        return None

    with caplog.at_level(logging.WARNING, logger="shoal.endpoint"):
        async with Endpoint(PUBLIC, on_time, port=0, clock=clock) as server:
            await post(url_of(server), COMMAND)
    assert "took" not in caplog.text


async def test_the_route_mounts_on_an_existing_application() -> None:
    handler = Recorder(None)
    server = Endpoint(PUBLIC, handler, path="/discord")
    app = web.Application()
    server.install(app)
    async with serve(app) as base:
        status, _ = await post(f"http://{base}/discord", COMMAND)
    assert status == 202
    assert len(handler.received) == 1


async def test_start_and_close_are_idempotent() -> None:
    server = Endpoint(PUBLIC, Recorder(None), port=0)
    with pytest.raises(RuntimeError, match="not listening"):
        _ = server.address
    async with server:
        address = server.address
        await asyncio.gather(server.start(), server.start())
        assert server.address == address
    await server.close()
    with pytest.raises(RuntimeError, match="not listening"):
        _ = server.address


async def test_a_failed_start_leaves_nothing_running() -> None:
    port = free_port()
    async with Endpoint(PUBLIC, Recorder(None), port=port):
        second = Endpoint(PUBLIC, Recorder(None), port=port)
        with pytest.raises(OSError):  # noqa: PT011 - the platform decides which OSError
            await second.start()
        with pytest.raises(RuntimeError, match="not listening"):
            _ = second.address


def webhook_event(event_type: str, data: JSONObject) -> JSONObject:
    event: JSONObject = {"type": event_type, "timestamp": "2024-10-18T14:42:53.064834", "data": data}
    return {"version": 1, "application_id": "11", "type": 1, "event": event}


def events_counted(metrics: InMemoryMetrics, event: str, result: str) -> float:
    return metrics.counters.get(
        InMemoryMetrics.key(HTTP_WEBHOOK_EVENTS, {"event": event, "result": result}), 0
    )


async def test_webhook_events_are_acknowledged_at_once_and_handled_after() -> None:
    metrics = InMemoryMetrics()
    received: list[WebhookEventPayload] = []
    release = asyncio.Event()

    async def events(payload: WebhookEventPayload) -> None:
        await release.wait()
        received.append(payload)

    async with Endpoint(PUBLIC, Recorder(None), port=0, events=events, metrics=metrics) as server:
        url = url_of(server, "/events")
        ping, ping_body = await post(url, {"version": 1, "application_id": "11", "type": 0})
        status, body = await post(url, webhook_event("APPLICATION_DEAUTHORIZED", {"user": USER}))
        assert received == []
        release.set()
        await settle()
    assert (ping, ping_body, status, body) == (204, b"", 204, b"")
    [payload] = received
    assert payload.type is WebhookPayloadType.EVENT
    assert events_counted(metrics, "ping", "accepted") == 1
    assert events_counted(metrics, "APPLICATION_DEAUTHORIZED", "accepted") == 1


async def test_webhook_events_are_verified_and_checked_like_interactions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    metrics = InMemoryMetrics()

    async def failing(payload: WebhookEventPayload) -> None:
        del payload
        msg = "boom"
        raise RuntimeError(msg)

    async with Endpoint(PUBLIC, Recorder(None), port=0, events=failing, metrics=metrics) as server:
        url = url_of(server, "/events")
        forged, _ = await post(url, webhook_event("ENTITLEMENT_CREATE", {}), signature="00" * 64)
        malformed, _ = await post(url, {"version": 1})
        with caplog.at_level(logging.ERROR, logger="shoal.endpoint"):
            newer, _ = await post(url, webhook_event("SOMETHING_NEW", {}))
            await settle()
    assert (forged, malformed, newer) == (401, 400, 204)
    assert events_counted(metrics, "unknown", "invalid_signature") == 1
    assert events_counted(metrics, "unknown", "malformed") == 1
    assert events_counted(metrics, "unknown", "handler_error") == 1
    assert "webhook event handler failed" in caplog.text


async def test_without_an_events_handler_there_is_no_events_route() -> None:
    async with Endpoint(PUBLIC, Recorder(None), port=0) as server:
        status, _ = await post(url_of(server, "/events"), {"version": 1, "application_id": "11", "type": 0})
    assert status == 404


async def test_max_age_refuses_a_recorded_request_sent_later() -> None:
    signed_at = 1_700_000_000.0
    for now, expected in ((signed_at + 5, 200), (signed_at + 600, 401)):
        clock = FakeClock(wall=now)
        async with Endpoint(PUBLIC, Recorder(None), port=0, max_age=60.0, clock=clock) as server:
            status, _ = await post(url_of(server), PING)
        assert status == expected
