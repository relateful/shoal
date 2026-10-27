"""Seeing the whole bot from any cluster: where each shard runs and how it is doing."""

import time

import shoal
from cluster.bot import ClusterBot
from shoal import commands


class Fleet(commands.Cog):
    """Commands answered by whichever cluster runs the guild's shard."""

    def __init__(self, bot: ClusterBot) -> None:
        self.bot = bot

    @commands.command()
    async def where(self, ctx: commands.Context) -> None:
        """Which shard and cluster this server is on."""
        manager = self.bot.shard_manager
        if ctx.guild is None or manager is None:
            return
        shard = (ctx.guild.id >> 22) % manager.shard_count
        await ctx.send(f"This server is on shard {shard}, run by **{self.bot.settings.name}**.")

    @commands.command()
    async def fleet(self, ctx: commands.Context) -> None:
        """Every shard of every cluster, from the shared shard directory."""
        statuses = await self.bot.directory.statuses(self.bot.settings.shard_count)
        now = time.time()
        lines: list[str] = []
        for shard_id in range(self.bot.settings.shard_count):
            status = statuses.get(shard_id)
            if status is None:
                lines.append(f"`{shard_id:>3}` missing: no cluster reported it in the last 15 s")
                continue
            latency = f" {status.latency * 1000:.0f} ms" if status.latency is not None else ""
            age = now - status.reported_at
            lines.append(
                f"`{shard_id:>3}` {status.cluster} · {status.state.name.lower()}{latency} · {age:.0f}s ago"
            )
        await ctx.send("\n".join(lines))

    @commands.command()
    async def servers(self, ctx: commands.Context) -> None:
        """How many servers the whole bot is in, read from the cache every cluster shares."""
        count = await self.bot.cache.guilds.size()
        await ctx.send(
            f"The bot is in {count} server(s) across {self.bot.settings.cluster_count} cluster(s)."
        )

    @commands.command()
    async def ping(self, ctx: commands.Context) -> None:
        latency = self.bot.latency
        shown = f" {latency * 1000:.0f} ms" if latency is not None else ""
        await ctx.send(
            f"Pong from {self.bot.settings.name}!{shown}", allowed_mentions=shoal.AllowedMentions.none()
        )


async def setup(bot: commands.Bot) -> None:
    if isinstance(bot, ClusterBot):
        await bot.add_cog(Fleet(bot))
