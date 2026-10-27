"""`python -m app.proxy`: the only process with the bot token for REST, and the rate limits.

Every other process sends its REST requests here with the proxy's secret. The proxy waits in one
rate limiter for all of them, so together they stay under Discord's per-bot limits.
"""

import asyncio
import logging
import os

from app.config import required
from shoal.rest import RestProxy, Token

log = logging.getLogger("app.proxy")


async def main() -> None:
    host = os.environ.get("PROXY_HOST", "127.0.0.1")
    port = int(os.environ.get("PROXY_PORT", "8080"))
    async with RestProxy(
        Token.bot(required("DISCORD_TOKEN")), secret=required("PROXY_SECRET"), host=host, port=port
    ):
        log.info("REST proxy on http://%s:%d/api", host, port)
        await asyncio.Event().wait()


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s proxy %(name)s: %(message)s")
asyncio.run(main())
