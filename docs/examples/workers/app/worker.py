"""`python -m app.worker`: the bot's logic, fed by the gateway process, with REST through the proxy.

A worker holds no gateway connection and no bot token. Restart it as often as you deploy: the
gateway keeps the shards connected meanwhile, and the worker picks the stream up again.
"""

import asyncio
import logging
import os
import platform

import shoal
from app.config import GATEWAY_HOST, GATEWAY_PORT, PROXY_URL, WORKER_SHARDS, required
from shoal import commands
from shoal.ipc import EventClient
from shoal.rest import RestClient

log = logging.getLogger("app.worker")
NAME = os.environ.get("WORKER_NAME", platform.node())
EVENTS = ["MESSAGE_CREATE", "INTERACTION_CREATE", "GUILD_CREATE", "GUILD_DELETE", "GUILD_UPDATE"]
"""What this worker needs; the gateway sends nothing else to it."""


class Worker(commands.Bot):
    def __init__(self) -> None:
        proxy_secret = required("PROXY_SECRET")
        super().__init__(
            "!",
            intents=shoal.Intents.default().with_flags(message_content=True),
            rest=lambda _token: RestClient(None, base_url=PROXY_URL, proxy_secret=proxy_secret),
        )

    async def run_worker(self) -> None:
        # The token passed to `login` is never used: every request goes through the proxy.
        await self.login("held-by-the-proxy")
        stream = EventClient(
            GATEWAY_HOST,
            GATEWAY_PORT,
            token=required("IPC_SECRET"),
            name=NAME,
            shard_ids=WORKER_SHARDS or None,
            events=EVENTS,
        )
        log.info("%s: handling %s", NAME, f"shards {WORKER_SHARDS}" if WORKER_SHARDS else "every shard")
        try:
            async with stream:
                async for event in stream:
                    await self.feed(event)
        finally:
            await self.close()


bot = Worker()


@bot.command()
async def ping(ctx: commands.Context) -> None:
    """Answered by a worker, sent through the proxy."""
    await ctx.send(f"Pong from worker **{NAME}**.")


@bot.command()
async def where(ctx: commands.Context) -> None:
    """Which process does what."""
    await ctx.send(
        "The gateway process received your message and streamed it here; "
        f"worker **{NAME}** ran this command; the REST proxy sent this reply."
    )


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s worker %(name)s: %(message)s")
asyncio.run(bot.run_worker())
