"""A discord.py bot moved to Shoal: the imports change, and the few lines marked CHANGED."""

import os

import shoal.compat as discord
from shoal.compat import app_commands, commands

# CHANGED: flags are immutable, so `intents.message_content = True` becomes `with_flags`.
intents = discord.Intents.default().with_flags(message_content=True, guild_members=True)
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user} ({bot.user.id if bot.user else '?'})")


@bot.command()
async def hello(ctx: commands.Context, member: discord.Member | None = None) -> None:
    who = member or ctx.author
    await ctx.send(f"Hello {who.mention}!", allowed_mentions=discord.AllowedMentions.none())


@bot.command()
@commands.has_permissions(manage_messages=True)
async def dm(ctx: commands.Context, member: discord.Member, *, text: str) -> None:
    try:
        await member.send(text)
    except discord.Forbidden:  # `ForbiddenError` in Shoal's own names
        await ctx.send("They don't accept DMs from me.")
    else:
        await ctx.send("Sent.")


@bot.tree.command(description="Server age")
async def created(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if guild is None:
        return
    stamp = discord.utils.format_dt(guild.created_at, style="R")
    await interaction.response.send_message(f"{guild.name} was created {stamp}.", ephemeral=True)


@bot.tree.context_menu(name="Avatar")
async def avatar(interaction: discord.Interaction, user: discord.Member | discord.User) -> None:
    await interaction.response.send_message(user.display_avatar.url, ephemeral=True)


@bot.command()
@commands.is_owner()
async def sync(ctx: commands.Context) -> None:
    """Sync the slash commands to this server (instant), or globally from a DM."""
    if ctx.guild is not None:
        bot.tree.copy_global_to(guild=ctx.guild.id)
    synced = await bot.tree.sync(guild=ctx.guild.id if ctx.guild else None)
    await ctx.send(f"Synced {len(synced)} command(s).")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: Exception) -> None:
    if isinstance(error, app_commands.CommandOnCooldownError):  # names end in `Error` in Shoal
        await interaction.response.send_message("Slow down.", ephemeral=True)
    else:
        raise error


bot.run(os.environ["DISCORD_TOKEN"])
