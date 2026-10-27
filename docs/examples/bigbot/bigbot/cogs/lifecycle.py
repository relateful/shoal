"""What happens to the bot itself: shards coming up, servers added and removed, command errors."""

import logging

import shoal
from shoal import commands

log = logging.getLogger(__name__)


class Lifecycle(commands.Cog):
    """Logs the bot's own events; a real bot would also alert on them."""

    @commands.Cog.listener()
    async def on_shard_ready(self, shard_id: int) -> None:
        log.info("shard %d ready", shard_id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: shoal.Guild) -> None:
        log.info("added to %s (%d), %s members", guild.name, guild.id, guild.member_count)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: shoal.Guild) -> None:
        log.info("removed from %s (%d)", guild.name, guild.id)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.CommandNotFoundError | commands.NotOwnerError):
            return
        if isinstance(error, commands.UserInputError | commands.CheckFailureError):
            await ctx.send(str(error))
            return
        log.error("command %s failed", ctx.command, exc_info=error)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Lifecycle())
