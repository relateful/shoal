"""Owner tools for running the bot: shard health, cache sizes, resharding, reloading, syncing."""

import time

from bigbot.bot import EXTENSIONS, BigBot
from shoal import commands


class Owner(commands.Cog):
    """Only the application's owner (or team) can use these."""

    def __init__(self, bot: BigBot) -> None:
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def shards(self, ctx: commands.Context) -> None:
        """Every shard's state and heartbeat latency."""
        manager = self.bot.shard_manager
        if manager is None:
            return
        lines = [
            f"`{status.shard_id:>4}` {status.state.name.lower():<12}"
            + (f" {status.latency * 1000:.0f} ms" if status.latency is not None else "")
            for status in manager.statuses()
        ]
        await ctx.send(f"**{manager.shard_count} shard(s)**\n" + "\n".join(lines))

    @commands.command()
    @commands.is_owner()
    async def stats(self, ctx: commands.Context) -> None:
        """Uptime and what the cache holds."""
        cache = self.bot.cache
        uptime = int(time.monotonic() - self.bot.started)
        # Async: a collection may live outside the process (Redis), shared by every cluster.
        sizes = {
            "guilds": await cache.guilds.size(),
            "channels": await cache.channels.size(),
            "members": await cache.members.size(),
            "users": await cache.users.size(),
            "messages": await cache.messages.size(),
        }
        cached = " · ".join(f"{name} {count:,}" for name, count in sizes.items())
        await ctx.send(f"Up {uptime // 3600}h {uptime % 3600 // 60}m\nCached: {cached}")

    @commands.command()
    @commands.is_owner()
    async def reshard(self, ctx: commands.Context, count: commands.Range[int, 1, 4096]) -> None:
        """Move to `count` shards without downtime: the new ones connect before the old ones close."""
        await ctx.send(f"Resharding to {count} shard(s); the current shards keep serving meanwhile.")
        try:
            await self.bot.reshard(count)
        except RuntimeError as error:  # another reshard is running
            await ctx.send(f"Could not reshard: {error}")
            return
        await ctx.send(f"Now running {count} shard(s).")

    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, name: str | None = None) -> None:
        """Reload one extension (`!reload general`), or all of them."""
        names = [f"bigbot.cogs.{name}"] if name else EXTENSIONS
        for extension in names:
            await self.bot.reload_extension(extension)
        await ctx.send(f"Reloaded {', '.join(names)}.")

    @commands.command()
    @commands.is_owner()
    async def sync(self, ctx: commands.Context, scope: str = "global") -> None:
        """Send the slash commands to Discord: `!sync` everywhere, `!sync here` to this server only."""
        if scope == "here" and ctx.guild is not None:
            self.bot.tree.copy_global_to(guild=ctx.guild.id)
            synced = await self.bot.tree.sync(guild=ctx.guild.id)
        else:
            synced = await self.bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} command(s) ({scope}).")

    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.NotOwnerError):
            return  # stay quiet: nobody else needs to know these exist
        if isinstance(error, commands.CommandInvokeError) and isinstance(
            error.original, commands.ExtensionError
        ):
            await ctx.send(f"Could not reload: {error.original}")
            return
        raise error


async def setup(bot: commands.Bot) -> None:
    if isinstance(bot, BigBot):
        await bot.add_cog(Owner(bot))
