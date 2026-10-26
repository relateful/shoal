"""An HTTP endpoint that receives interactions from Discord, for bots without a gateway connection.

    async def handle(interaction: Interaction | UnknownInteraction) -> InteractionResponse | None:
        if isinstance(interaction, ApplicationCommandInteraction):
            return MessageResponse(data=InteractionMessage(content="pong"))
        return None

    async with InteractionServer(public_key, handle):
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
from typing import Final, Self, final

from aiohttp import web

from shoal.core.clock import Clock, SystemClock
from shoal.core.codec import PayloadDecodeError, encode_json
from shoal.core.metrics import HTTP_INTERACTION_SECONDS, HTTP_INTERACTIONS, Metrics, NoopMetrics
from shoal.interaction_server.defaults import HANDLER_TIMEOUT, HOST, PATH, PORT
from shoal.interaction_server.signature import SignatureVerifier
from shoal.payloads.application import InteractionType
from shoal.payloads.interactions import (
    INTERACTION_RESPONSE_DEADLINE,
    ApplicationCommandInteraction,
    AutocompleteInteraction,
    ComponentInteraction,
    Interaction,
    InteractionResponse,
    ModalSubmitInteraction,
    PingInteraction,
    PongResponse,
    UnknownInteraction,
    parse_interaction,
)

_log = logging.getLogger("shoal.interaction_server")

type InteractionHandler = Callable[[Interaction | UnknownInteraction], Awaitable[InteractionResponse | None]]
"""Answers one interaction: return the response to send inline, or `None` after answering through
the callback endpoint yourself."""

_JSON = "application/json"


@final
class InteractionServer:
    """Receives interactions over HTTP and hands them to `handler`.

    Args:
        public_key: The application's public key from the Developer Portal (hex).
        handler: Called with each verified interaction except `PING`.
        host: Address to listen on. Keep the default and put a TLS reverse proxy in front.
        port: Port to listen on; `0` picks a free one (see `address`).
        path: URL path Discord posts to; configure the same in the Developer Portal.
        handler_timeout: Seconds a handler may run before the server replies 500 without it.
        metrics: Receives `shoal_http_interactions_total` and `shoal_http_interaction_seconds`.
        clock: Time source for measuring handlers.

    Importing this module raises `MissingDependencyError` when `shoal[interactions]` is not installed.

    Raises:
        ValueError: `public_key` is not a valid Ed25519 public key.
    """

    __slots__ = (
        "_clock",
        "_handler",
        "_handler_timeout",
        "_host",
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
        handler: InteractionHandler,
        *,
        host: str = HOST,
        port: int = PORT,
        path: str = PATH,
        handler_timeout: float = HANDLER_TIMEOUT,
        metrics: Metrics | None = None,
        clock: Clock | None = None,
    ) -> None:
        """Create a server; see the class docstring for the arguments. Call `start` to listen."""
        self._verifier: SignatureVerifier = SignatureVerifier(public_key)
        self._handler: InteractionHandler = handler
        self._host: str = host
        self._port: int = port
        self._path: str = path
        self._handler_timeout: float = handler_timeout
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
            msg = "the InteractionServer is not listening"
            raise RuntimeError(msg)
        host, port = addresses[0][:2]
        return str(host), int(port)

    def install(self, app: web.Application) -> None:
        """Add the interaction route to an existing aiohttp application, such as a dashboard's."""
        app.router.add_post(self._path, self.handle)

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
        _log.info("interaction server listening on %s:%d%s", *self.address, self._path)

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
        signature = request.headers.get("X-Signature-Ed25519", "")
        timestamp = request.headers.get("X-Signature-Timestamp", "")
        if not self._verifier.verify(signature=signature, timestamp=timestamp, body=body):
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
        try:
            async with asyncio.timeout(self._handler_timeout):
                response = await self._handler(interaction)
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
        return self._finish(label, started, "inline", web.Response(body=reply, content_type=_JSON))

    def _finish(self, label: str, started: float, result: str, response: web.Response) -> web.Response:
        """Record how a handled interaction ended, and pass its HTTP response through."""
        elapsed = self._clock.monotonic() - started
        self._metrics.observe(HTTP_INTERACTION_SECONDS, elapsed, {"type": label})
        self._metrics.increment(HTTP_INTERACTIONS, {"type": label, "result": result})
        return response


_LABELS: Final[dict[type[Interaction], InteractionType]] = {
    ApplicationCommandInteraction: InteractionType.APPLICATION_COMMAND,
    AutocompleteInteraction: InteractionType.APPLICATION_COMMAND_AUTOCOMPLETE,
    ComponentInteraction: InteractionType.MESSAGE_COMPONENT,
    ModalSubmitInteraction: InteractionType.MODAL_SUBMIT,
    PingInteraction: InteractionType.PING,
}
"""Each interaction class and its type, for metric labels."""


def _label(interaction: Interaction | UnknownInteraction) -> str:
    """The metric label for an interaction's type: its name in lower case, or `unknown`."""
    if isinstance(interaction, UnknownInteraction):
        return "unknown"
    return _LABELS[type(interaction)].name.lower()
