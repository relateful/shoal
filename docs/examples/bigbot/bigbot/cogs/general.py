"""Commands for everyone."""

import shoal
from bigbot.bot import BigBot
from shoal import commands


class General(commands.Cog):
    """Everyday commands."""

    def __init__(self, bot: BigBot) -> None:
        self.bot = bot

    @commands.hybrid_command(description="Check the bot is alive")
    async def ping(self, ctx: commands.Context) -> None:
        latency = self.bot.latency
        await ctx.send(f"Pong! {latency * 1000:.0f} ms" if latency is not None else "Pong!")

    @commands.hybrid_command(description="About this bot")
    async def about(self, ctx: commands.Context) -> None:
        manager = self.bot.shard_manager
        shard = manager.shard_for_guild(ctx.guild.id) if manager is not None and ctx.guild is not None else 0
        embed = shoal.Embed(title=self.bot.user.name if self.bot.user else "bigbot", colour=0x5865F2)
        embed.add_field(name="Servers", value=f"{await self.bot.cache.guilds.size():,}")
        embed.add_field(name="Shard", value=f"{shard} of {manager.shard_count if manager else 1}")
        embed.add_field(name="Library", value=f"Shoal {shoal.__version__}")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    if isinstance(bot, BigBot):
        await bot.add_cog(General(bot))
