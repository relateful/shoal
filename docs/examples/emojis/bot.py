"""Application emojis: a folder of images uploaded as the bot's own emojis, used by name."""

import os
from pathlib import Path

import shoal
from shoal import app_commands
from shoal.client import Client
from shoal.emojis import AppEmojis, app_emoji

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
FOLDER = Path(__file__).with_name("emojis")


class Icons(AppEmojis):
    """Each name matches an image in emojis/; the unicode shows until it is uploaded."""

    shoal_online = app_emoji("🟢")
    shoal_offline = app_emoji("🔴")


icons = Icons()


class Bot(Client):
    def __init__(self) -> None:
        super().__init__(intents=shoal.Intents.default(), app_emojis=icons)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        # Upload what changed in emojis/ (unchanged images are skipped), then fetch the emojis.
        report = await icons.sync(FOLDER)
        print(report)
        if GUILD_ID:
            self.tree.copy_global_to(guild=int(GUILD_ID))
            await self.tree.sync(guild=int(GUILD_ID))
        else:
            await self.tree.sync()


bot = Bot()


@bot.tree.command(description="Show the status of a few services")
async def status(interaction: shoal.Interaction) -> None:
    services = {"Website": True, "API": True, "Database": False}
    lines = [f"{icons.shoal_online if up else icons.shoal_offline} {name}" for name, up in services.items()]
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(description="React with the bot's own emoji")
async def wave(interaction: shoal.Interaction) -> None:
    await interaction.response.send_message("Hello!")
    message = await interaction.original_response()
    await message.add_reaction(icons.shoal_online)


bot.run(os.environ["DISCORD_TOKEN"])
