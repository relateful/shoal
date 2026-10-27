"""`python -m app.gateway`: the shards, and nothing else. Every event goes to the workers over IPC.

It never runs bot logic, so deploying new features restarts only the workers: the shards stay
connected, and no session is lost.
"""

import asyncio
import logging
import os

from app.config import GATEWAY_HOST, GATEWAY_PORT, PROXY_URL, required
from shoal.gateway import FileSessionStore, LocalIdentifyLimiter, ShardManager
from shoal.ipc import EventServer
from shoal.payloads import Intents
from shoal.rest import RestClient

log = logging.getLogger("app.gateway")


async def main() -> None:
    token = required("DISCORD_TOKEN")  # identifying needs it; REST still goes through the proxy
    async with RestClient(None, base_url=PROXY_URL, proxy_secret=required("PROXY_SECRET")) as rest:
        gateway = await rest.gateway.get_bot()
    server = EventServer(token=required("IPC_SECRET"), host=GATEWAY_HOST, port=GATEWAY_PORT)
    await server.start()
    log.info("streaming events on %s:%d", GATEWAY_HOST, GATEWAY_PORT)
    manager = ShardManager(
        token=token,
        intents=Intents.default().with_flags(message_content=True),
        dispatch=server.publish,
        shard_count=gateway.shards,
        gateway_url=gateway.url,
        identify_limiter=LocalIdentifyLimiter(gateway.session_start_limit.max_concurrency),
        session_store=FileSessionStore(os.environ.get("SESSIONS_DIR", "sessions")),
    )
    try:
        await manager.run()
    finally:
        await manager.close()  # keeps the sessions resumable and saves them
        await server.close()


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s gateway %(name)s: %(message)s")
asyncio.run(main())
