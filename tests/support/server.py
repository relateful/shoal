"""A real aiohttp server on loopback, for testing Shoal's aiohttp adapters end to end."""

import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from aiohttp import web


def free_port() -> int:
    """A loopback port nothing is listening on right now."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@asynccontextmanager
async def serve(app: web.Application) -> AsyncGenerator[str]:
    """Run `app` on a free loopback port and yield its base URL."""
    runner = web.AppRunner(app)
    await runner.setup()
    port = free_port()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        yield f"127.0.0.1:{port}"
    finally:
        await runner.cleanup()
