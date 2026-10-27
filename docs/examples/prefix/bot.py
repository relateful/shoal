"""Prefix commands: converters, flags, groups, checks, cooldowns, and friendly errors."""

import os
from typing import Annotated

import shoal
from shoal import commands

intents = shoal.Intents.default().with_flags(message_content=True, guild_members=True)
bot = commands.Bot("!", intents=intents, description="A prefix command tour", case_insensitive=True)


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user}; try !help")


@bot.command()
async def add(ctx: commands.Context, *numbers: float) -> None:
    """Add any amount of numbers: !add 1 2 3.5"""
    await ctx.send(f"{sum(numbers):g}")


@bot.command(aliases=["whois"])
async def userinfo(ctx: commands.Context, who: shoal.Member | shoal.User = commands.Author) -> None:
    """Show who someone is: !userinfo @someone (or just !userinfo)."""
    embed = shoal.Embed(title=who.display_name, colour=0x5865F2)
    embed.set_thumbnail(url=who.display_avatar.url)
    embed.add_field(name="Account created", value=f"<t:{int(who.created_at.timestamp())}:R>")
    if isinstance(who, shoal.Member):
        if who.joined_at is not None:
            embed.add_field(name="Joined", value=f"<t:{int(who.joined_at.timestamp())}:R>")
        roles = " ".join(role.mention for role in who.roles if not role.is_default())
        embed.add_field(name="Roles", value=roles or "none", inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def echo(ctx: commands.Context, *, text: Annotated[str, commands.clean_content()]) -> None:
    """Repeat a message; mentions are written out so they ping nobody."""
    await ctx.send(text)


class PollFlags(commands.FlagConverter):
    question: str
    options: list[str] = commands.flag(name="option", default=[])


@bot.command()
async def quickpoll(ctx: commands.Context, *, flags: PollFlags) -> None:
    """!quickpoll question: Lunch? option: pizza option: sushi"""
    lines = [f"{index + 1}. {option}" for index, option in enumerate(flags.options)]
    await ctx.send(f"**{flags.question}**\n" + "\n".join(lines))


@bot.group(invoke_without_command=True)
async def tag(ctx: commands.Context) -> None:
    """Tags: !tag add name text, !tag show name."""
    await ctx.send_help(ctx.command)


TAGS: dict[str, str] = {}


@tag.command(name="add")
async def tag_add(ctx: commands.Context, name: str, *, text: str) -> None:
    TAGS[name.lower()] = text
    await ctx.send(f"Saved tag `{name}`.")


@tag.command(name="show")
async def tag_show(ctx: commands.Context, name: str) -> None:
    await ctx.send(TAGS.get(name.lower(), "No such tag."))


@bot.command()
@commands.guild_only()
@commands.has_permissions(manage_messages=True)
@commands.cooldown(1, 10, commands.BucketType.CHANNEL)
async def clean(ctx: commands.Context, amount: commands.Range[int, 1, 100] = 10) -> None:
    """Delete the bot's own recent messages (Manage Messages)."""
    if not isinstance(ctx.channel, shoal.TextChannel) or bot.user is None:
        return
    me = bot.user.id
    deleted = await ctx.channel.purge(limit=amount, check=lambda message: message.author.id == me)
    await ctx.send(f"Removed {len(deleted)} message(s).", delete_after=5)


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.CommandNotFoundError):
        return
    if isinstance(error, commands.CommandOnCooldownError):
        await ctx.send(f"Slow down! Try again in {error.retry_after:.0f}s.")
    elif isinstance(error, commands.MissingPermissionsError):
        await ctx.send(f"You need: {', '.join(error.missing_permissions)}.")
    elif isinstance(error, commands.UserInputError) and ctx.command is not None:
        usage = f"{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}"
        await ctx.send(f"{error}\nUsage: `{usage.strip()}`")
    else:
        raise error


bot.run(os.environ["DISCORD_TOKEN"])
