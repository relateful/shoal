"""Hybrid commands: one definition that works as both !command and /command."""

import os
import random

import shoal
from shoal import app_commands, commands

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")


class Bot(commands.Bot):
    def __init__(self) -> None:
        intents = shoal.Intents.default().with_flags(message_content=True)
        super().__init__(commands.when_mentioned_or("?"), intents=intents)

    async def setup_hook(self) -> None:
        if GUILD_ID:
            self.tree.copy_global_to(guild=int(GUILD_ID))
            await self.tree.sync(guild=int(GUILD_ID))
        else:
            await self.tree.sync()


bot = Bot()


@bot.hybrid_command(description="Flip a coin")
async def flip(ctx: commands.Context) -> None:
    await ctx.send(random.choice(["Heads!", "Tails!"]))


@bot.hybrid_command(description="Pick one of several choices")
@app_commands.describe(choices="Choices separated by commas")
async def choose(ctx: commands.Context, *, choices: str) -> None:
    options = [choice.strip() for choice in choices.split(",") if choice.strip()]
    await ctx.send(
        f"I choose **{random.choice(options)}**" if options else "Give me something to choose from."
    )


BIOS: dict[int, str] = {}


@bot.hybrid_group(description="Your profile", invoke_without_command=True)
async def profile(ctx: commands.Context) -> None:
    # Runs for a bare `?profile`; a slash group is always used through a subcommand.
    await ctx.send_help(ctx.command)


@profile.command(description="Show your profile")
async def show(ctx: commands.Context) -> None:
    bio = BIOS.get(ctx.author.id, "No bio yet; set one with /profile bio.")
    # Only the person who asked sees a slash answer marked ephemeral; a prefix answer is public.
    await ctx.send(f"**{ctx.author.display_name}**: {bio}", ephemeral=True)


@profile.command(description="Set your bio")
async def bio(ctx: commands.Context, *, text: commands.Range[str, 1, 100]) -> None:
    BIOS[ctx.author.id] = text
    await ctx.send("Bio saved.", ephemeral=True)


@bot.hybrid_command(description="Answer after a slow task")
async def slow(ctx: commands.Context) -> None:
    # `defer` shows "thinking…" for a slash command and "typing…" for a prefix command.
    await ctx.defer()
    await ctx.send(f"Done: {sum(range(1_000_000))}")


bot.run(os.environ["DISCORD_TOKEN"])
