"""An HTTP endpoint that receives interactions from Discord, for bots without a gateway connection.

    async def handle(interaction: Interaction | UnknownInteraction) -> InteractionResponse | None:
        if isinstance(interaction, ApplicationCommandInteraction):
            return MessageResponse(data=InteractionMessage(content="pong"))
        return None

    async with Endpoint(public_key, handle):
        await asyncio.Event().wait()

Every request is checked against the application's public key before anything else runs. `PING`
is answered by the server. Everything else goes to the handler, which either returns a response
(sent back in the HTTP reply) or `None` after answering through `RestClient.interactions.respond`
(the server then replies `202`, as Discord requires).

Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#receiving-an-interaction
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Self, final

from aiohttp import web
from msgspec import UnsetType

from shoal.core.clock import Clock, SystemClock, within
from shoal.core.codec import PayloadDecodeError, decode_json, encode_json
from shoal.core.metrics import (
    HTTP_INTERACTION_SECONDS,
    HTTP_INTERACTIONS,
    HTTP_WEBHOOK_EVENTS,
    Metrics,
    NoopMetrics,
)
from shoal.core.replies import REPLY_WRITTEN
from shoal.core.tasks import spawn
from shoal.endpoint.defaults import EVENTS_PATH, HANDLER_TIMEOUT, HOST, PATH, PORT
from shoal.endpoint.signature import SignatureVerifier
from shoal.payloads.interactions import (
    INTERACTION_RESPONSE_DEADLINE,
    INTERACTION_TYPES,
    Interaction,
    InteractionResponse,
    PingInteraction,
    PongResponse,
    UnknownInteraction,
    parse_interaction,
)
from shoal.payloads.webhook_events import WEBHOOK_EVENT_PAYLOADS, WebhookEventPayload, WebhookPayloadType

_log = logging.getLogger("shoal.endpoint")

type EndpointHandler = Callable[[Interaction | UnknownInteraction], Awaitable[InteractionResponse | None]]
"""Answers one interaction: return the response to send inline, or `None` after answering through
the callback endpoint yourself."""

type WebhookEventHandler = Callable[[WebhookEventPayload], Awaitable[None]]
"""Handles one webhook event; `event.data` decodes with the type `WEBHOOK_EVENT_PAYLOADS` gives."""

_JSON = "application/json"


@final
class Endpoint:
    """Receives interactions over HTTP and hands them to `handler`.

    Args:
        public_key: The application's public key from the Developer Portal (hex).
        handler: Called with each verified interaction except `PING`.
        host: Address to listen on. Keep the default and put a TLS reverse proxy in front.
        port: Port to listen on; `0` picks a free one (see `address`).
        path: URL path Discord posts to; configure the same in the Developer Portal.
        handler_timeout: Seconds a handler may run before the server replies 500 without it.
        events: Called with each verified webhook event (not `PING`), in its own task: the server
            acknowledges every event with `204` at once, as Discord retries one not acknowledged
            within 3 seconds. `None` serves no webhook events.
        events_path: URL path of the app's Webhook Events URL.
        max_age: Refuse (`401`) a signed request whose timestamp is further than this many seconds
            from now, so a recorded request cannot be sent again later. `None` (the default) checks
            only the signature, as Discord asks; set it when the server's clock is kept in sync.
        metrics: Receives `shoal_http_interactions_total`, `shoal_http_interaction_seconds` and
            `shoal_http_webhook_events_total`.
        clock: Time source for measuring handlers.

    Importing this module raises `MissingDependencyError` when `shoal[interactions]` is not installed.

    Raises:
        ValueError: `public_key` is not a valid Ed25519 public key.
    """

    __slots__ = (
        "_clock",
        "_events",
        "_events_path",
        "_handler",
        "_handler_timeout",
        "_host",
        "_max_age",
        "_metrics",
        "_path",
        "_port",
        "_runner",
        "_start_lock",
        "_verifier",
    )

    def __init__(
        self,
        public_key: str,
        handler: EndpointHandler,
        *,
        host: str = HOST,
        port: int = PORT,
        path: str = PATH,
        handler_timeout: float = HANDLER_TIMEOUT,
        events: WebhookEventHandler | None = None,
        events_path: str = EVENTS_PATH,
        max_age: float | None = None,
        metrics: Metrics | None = None,
        clock: Clock | None = None,
    ) -> None:
        """Create a server; see the class docstring for the arguments. Call `start` to listen."""
        self._verifier: SignatureVerifier = SignatureVerifier(public_key)
        self._handler: EndpointHandler = handler
        self._host: str = host
        self._port: int = port
        self._path: str = path
        self._handler_timeout: float = handler_timeout
        self._events: WebhookEventHandler | None = events
        self._events_path: str = events_path
        self._max_age: float | None = max_age
        self._metrics: Metrics = metrics or NoopMetrics()
        self._clock: Clock = clock or SystemClock()
        self._runner: web.AppRunner | None = None
        self._start_lock: asyncio.Lock = asyncio.Lock()

    @property
    def address(self) -> tuple[str, int]:
        """The host and port the server listens on.

        Raises:
            RuntimeError: The server has not been started.
        """
        addresses = self._runner.addresses if self._runner is not None else []
        if not addresses:
            msg = "the endpoint is not listening"
            raise RuntimeError(msg)
        host, port = addresses[0][:2]
        return str(host), int(port)

    def install(self, app: web.Application) -> None:
        """Add the routes to an existing aiohttp application, such as a dashboard's.

        The webhook events route is added only when there is an `events` handler.
        """
        app.router.add_post(self._path, self.handle)
        if self._events is not None:
            app.router.add_post(self._events_path, self.handle_event)

    async def start(self) -> None:
        """Start listening. Idempotent, and safe to call concurrently.

        Raises:
            OSError: The address could not be bound, such as a port already in use.
        """
        async with self._start_lock:
            if self._runner is not None:
                return
            app = web.Application()
            self.install(app)
            runner = web.AppRunner(app, access_log=None)
            await runner.setup()
            try:
                await web.TCPSite(runner, self._host, self._port).start()
            except BaseException:
                await runner.cleanup()
                raise
            self._runner = runner
        _log.info("endpoint listening on %s:%d%s", *self.address, self._path)

    async def close(self) -> None:
        """Stop listening. Idempotent."""
        runner, self._runner = self._runner, None
        if runner is not None:
            await runner.cleanup()

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
        """Answer one POST from Discord. Public so frameworks other than `install` can call it."""
        body = await request.read()
        if not self._verified(request, body):
            # Discord sends invalid requests on purpose to test the endpoint, so this is not a warning.
            _log.debug("rejected an interaction request with an invalid signature")
            self._metrics.increment(HTTP_INTERACTIONS, {"type": "unknown", "result": "invalid_signature"})
            return web.Response(status=401, text="invalid request signature")
        try:
            interaction = parse_interaction(body)
        except PayloadDecodeError:
            _log.warning("signed interaction request could not be decoded", exc_info=True)
            self._metrics.increment(HTTP_INTERACTIONS, {"type": "unknown", "result": "malformed"})
            return web.Response(status=400, text="malformed interaction")
        label = _label(interaction)
        if isinstance(interaction, PingInteraction):
            self._metrics.increment(HTTP_INTERACTIONS, {"type": label, "result": "inline"})
            return web.Response(body=encode_json(PongResponse()), content_type=_JSON)
        started = self._clock.monotonic()
        written: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        try:
            return await self._answer(request, interaction, label, started, written)
        finally:
            if not written.done():
                written.set_result(None)

    async def _answer(
        self,
        request: web.Request,
        interaction: Interaction | UnknownInteraction,
        label: str,
        started: float,
        written: asyncio.Future[None],
    ) -> web.Response:
        reset = REPLY_WRITTEN.set(written)
        try:
            response = await within(self._clock, self._handler_timeout, self._handler(interaction))
            reply = None if response is None else encode_json(response)
        except TimeoutError:
            _log.error(
                "interaction handler for %s interaction %s did not finish within %.0fs",
                label,
                interaction.id,
                self._handler_timeout,
            )
            return self._finish(label, started, "timeout", web.Response(status=500, text="handler timed out"))
        except Exception:  # noqa: BLE001 - one failing handler must not take the endpoint down
            _log.exception("interaction handler failed for %s interaction %s", label, interaction.id)
            return self._finish(
                label, started, "handler_error", web.Response(status=500, text="handler failed")
            )
        finally:
            REPLY_WRITTEN.reset(reset)
        elapsed = self._clock.monotonic() - started
        if elapsed > INTERACTION_RESPONSE_DEADLINE:
            _log.warning(
                "interaction handler took %.2fs for %s interaction %s; Discord fails interactions not "
                "answered within %.0fs (defer first, then edit the response)",
                elapsed,
                label,
                interaction.id,
                INTERACTION_RESPONSE_DEADLINE,
            )
        if reply is None:
            return self._finish(label, started, "callback", web.Response(status=202))
        # Written here rather than after returning, so code waiting on `REPLY_WRITTEN` resumes only
        # once Discord has the response.
        sent = web.Response(body=reply, content_type=_JSON)
        await sent.prepare(request)
        await sent.write_eof()
        written.set_result(None)
        return self._finish(label, started, "inline", sent)

    async def handle_event(self, request: web.Request) -> web.Response:
        """Answer one webhook event POST from Discord. Public so other frameworks can call it."""
        body = await request.read()
        if not self._verified(request, body):
            _log.debug("rejected a webhook event request with an invalid signature")
            self._metrics.increment(HTTP_WEBHOOK_EVENTS, {"event": "unknown", "result": "invalid_signature"})
            return web.Response(status=401, text="invalid request signature")
        try:
            payload = decode_json(body, WebhookEventPayload)
        except PayloadDecodeError:
            _log.warning("signed webhook event request could not be decoded", exc_info=True)
            self._metrics.increment(HTTP_WEBHOOK_EVENTS, {"event": "unknown", "result": "malformed"})
            return web.Response(status=400, text="malformed webhook event")
        event = payload.event
        if payload.type is WebhookPayloadType.PING or isinstance(event, UnsetType):
            self._metrics.increment(HTTP_WEBHOOK_EVENTS, {"event": "ping", "result": "accepted"})
            return web.Response(status=204)
        label = event.type.value if event.type in WEBHOOK_EVENT_PAYLOADS else "unknown"
        handler = self._events
        if handler is not None:
            _ = spawn(self._run_event(handler, payload, label), name=f"shoal-webhook-event-{label}")
        self._metrics.increment(HTTP_WEBHOOK_EVENTS, {"event": label, "result": "accepted"})
        return web.Response(status=204)

    async def _run_event(
        self, handler: WebhookEventHandler, payload: WebhookEventPayload, label: str
    ) -> None:
        try:
            await handler(payload)
        except Exception:  # noqa: BLE001 - one failing handler must not take the endpoint down
            _log.exception("webhook event handler failed for %s", label)
            self._metrics.increment(HTTP_WEBHOOK_EVENTS, {"event": label, "result": "handler_error"})

    def _verified(self, request: web.Request, body: bytes) -> bool:
        """Whether Discord signed `body`, and (with `max_age`) recently enough."""
        signature = request.headers.get("X-Signature-Ed25519", "")
        timestamp = request.headers.get("X-Signature-Timestamp", "")
        if not self._verifier.verify(signature=signature, timestamp=timestamp, body=body):
            return False
        if self._max_age is None:
            return True
        # The signature covers the timestamp, so an old one is a request recorded and sent again.
        return timestamp.isdigit() and abs(self._clock.wall() - int(timestamp)) <= self._max_age

    def _finish(self, label: str, started: float, result: str, response: web.Response) -> web.Response:
        """Record how a handled interaction ended, and pass its HTTP response through."""
        elapsed = self._clock.monotonic() - started
        self._metrics.observe(HTTP_INTERACTION_SECONDS, elapsed, {"type": label})
        self._metrics.increment(HTTP_INTERACTIONS, {"type": label, "result": result})
        return response


def _label(interaction: Interaction | UnknownInteraction) -> str:
    """The metric label for an interaction's type: its name in lower case, or `unknown`."""
    if isinstance(interaction, UnknownInteraction):
        return "unknown"
    return INTERACTION_TYPES[type(interaction)].name.lower()
