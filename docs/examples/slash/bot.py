"""Slash commands with options, choices, autocomplete, a group and a context menu."""

import os
import random

import shoal
from shoal import app_commands
from shoal.app_commands import Choice, Range
from shoal.client import Client

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
"""Set it while developing: commands synced to one server show up at once."""

FRUITS = ["apple", "apricot", "banana", "blackberry", "cherry", "grape", "lemon", "mango", "peach"]


class Bot(Client):
    def __init__(self) -> None:
        super().__init__(intents=shoal.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self.tree.add_command(Notes())
        if GUILD_ID:
            self.tree.copy_global_to(guild=int(GUILD_ID))
            await self.tree.sync(guild=int(GUILD_ID))
        else:
            await self.tree.sync()


bot = Bot()


@bot.tree.command(description="Roll some dice")
@app_commands.describe(dice="How many dice", sides="Sides on each die")
async def roll(
    interaction: shoal.Interaction, dice: Range[int, 1, 10] = 1, sides: Range[int, 2, 100] = 6
) -> None:
    rolls = [random.randint(1, sides) for _ in range(dice)]
    await interaction.response.send_message(f"🎲 {', '.join(map(str, rolls))} (total {sum(rolls)})")


@bot.tree.command(description="Pick a colour")
@app_commands.choices(colour=[Choice(name="Red", value="#ed4245"), Choice(name="Blurple", value="#5865f2")])
async def colour(interaction: shoal.Interaction, colour: str) -> None:
    await interaction.response.send_message(f"You picked {colour}", ephemeral=True)


@bot.tree.command(description="Find a fruit")
async def fruit(interaction: shoal.Interaction, name: str) -> None:
    await interaction.response.send_message(f"🍓 {name}")


@fruit.autocomplete("name")
async def fruit_names(interaction: shoal.Interaction, current: str) -> list[Choice[str]]:
    return [Choice(name=name, value=name) for name in FRUITS if current.lower() in name][:25]


class Notes(app_commands.Group, name="notes", description="Keep short notes"):
    def __init__(self) -> None:
        super().__init__()
        self.notes: dict[int, list[str]] = {}

    @app_commands.command(description="Add a note")
    async def add(self, interaction: shoal.Interaction, text: str) -> None:
        self.notes.setdefault(interaction.user.id, []).append(text)
        await interaction.response.send_message("Saved.", ephemeral=True)

    @app_commands.command(description="List your notes")
    async def list(self, interaction: shoal.Interaction) -> None:
        mine = self.notes.get(interaction.user.id) or ["(none yet)"]
        await interaction.response.send_message("\n".join(f"• {note}" for note in mine), ephemeral=True)


@bot.tree.context_menu(name="Account age")
async def account_age(interaction: shoal.Interaction, member: shoal.Member | shoal.User) -> None:
    await interaction.response.send_message(
        f"{member.mention} joined Discord <t:{int(member.created_at.timestamp())}:R>", ephemeral=True
    )


bot.run(os.environ["DISCORD_TOKEN"])
