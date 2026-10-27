"""Proving the safeguards work: owner commands that block the event loop and burst messages on purpose."""

import asyncio
import time

from bigbot.bot import BigBot
from shoal import commands


class Diagnostics(commands.Cog):
    """Owner-only checks of the bot's health tooling."""

    def __init__(self, bot: BigBot) -> None:
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def block(self, ctx: commands.Context, seconds: commands.Range[float, 0.1, 5.0] = 1.0) -> None:
        """Block the event loop for `seconds`, as a slow synchronous call would.

        Watch the log: while it blocks, the watchdog names this line as the culprit, and the block
        lands in `shoal_loop_blocks_total` and `shoal_loop_block_seconds`. Never do this for real:
        every shard's heartbeat waits meanwhile.
        """
        await ctx.send(f"Blocking the event loop for {seconds:g}s…")
        time.sleep(seconds)  # noqa: ASYNC251 - the point of this command
        await ctx.send("Done. The watchdog's report is in the log.")

    @commands.command()
    @commands.is_owner()
    async def burst(self, ctx: commands.Context, count: commands.Range[int, 2, 20] = 10) -> None:
        """Send `count` messages at once: the rate limiter spaces them out instead of hitting 429s.

        Discord allows about five messages per channel every few seconds; the rest wait for the
        bucket to refill. `shoal_rest_rate_limited_total` counts any 429 that still got through.
        """
        started = time.monotonic()
        await asyncio.gather(*(ctx.channel.send(f"burst {index + 1}/{count}") for index in range(count)))
        await ctx.send(f"Sent {count} messages in {time.monotonic() - started:.1f}s.")


async def setup(bot: commands.Bot) -> None:
    if isinstance(bot, BigBot):
        await bot.add_cog(Diagnostics(bot))
