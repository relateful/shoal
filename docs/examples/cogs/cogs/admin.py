"""Owner tools: load, unload and reload extensions while the bot runs."""

from shoal import commands


class Admin(commands.Cog):
    """Owner-only tools."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, name: str) -> None:
        """Reload an extension: !reload fun"""
        await self.bot.reload_extension(f"cogs.{name}")
        await ctx.send(f"Reloaded `{name}`.")

    @commands.command()
    @commands.is_owner()
    async def unload(self, ctx: commands.Context, name: str) -> None:
        """Unload an extension, its slash commands included: !unload fun"""
        await self.bot.unload_extension(f"cogs.{name}")
        await ctx.send(f"Unloaded `{name}`.")

    @commands.command()
    @commands.is_owner()
    async def load(self, ctx: commands.Context, name: str) -> None:
        """Load an extension: !load fun"""
        await self.bot.load_extension(f"cogs.{name}")
        await ctx.send(f"Loaded `{name}`.")

    @commands.command()
    @commands.is_owner()
    async def sync(self, ctx: commands.Context) -> None:
        """Send the slash commands to Discord again, here."""
        if ctx.guild is None:
            return
        self.bot.tree.copy_global_to(guild=ctx.guild.id)
        synced = await self.bot.tree.sync(guild=ctx.guild.id)
        await ctx.send(f"Synced {len(synced)} commands.")

    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.NotOwnerError):
            await ctx.send("Only the bot's owner can do that.")
        elif isinstance(error, commands.CommandInvokeError) and isinstance(
            error.original, commands.ExtensionError
        ):
            await ctx.send(f"Could not do that: {error.original}")
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
