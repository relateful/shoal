"""A bot without a gateway connection: Discord sends interactions to this web server."""

import asyncio
import os
import random

import shoal
from shoal import app_commands, ui
from shoal.client import Client

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
PUBLIC_KEY = os.environ["DISCORD_PUBLIC_KEY"]
"""From the Developer Portal: General Information → Public Key. Used to check every request."""
PORT = int(os.environ.get("PORT", "8080"))


class Bot(Client):
    def __init__(self) -> None:
        # No intents needed: nothing connects to the gateway.
        super().__init__(intents=shoal.Intents.none())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        if GUILD_ID:
            self.tree.copy_global_to(guild=int(GUILD_ID))
            await self.tree.sync(guild=int(GUILD_ID))
        else:
            await self.tree.sync()


bot = Bot()


class Counter(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=300)
        self.count = 0

    @ui.button(label="+1", style=shoal.ButtonStyle.PRIMARY)
    async def add(self, interaction: shoal.Interaction, button: ui.Button) -> None:
        self.count += 1
        await interaction.response.edit_message(content=f"Count: {self.count}", view=self)


@bot.tree.command(description="Roll a die, served over HTTP")
async def roll(interaction: shoal.Interaction) -> None:
    await interaction.response.send_message(f"🎲 {random.randint(1, 6)}")


@bot.tree.command(description="A button that counts")
async def counter(interaction: shoal.Interaction) -> None:
    await interaction.response.send_message("Count: 0", view=Counter())


@bot.tree.command(description="Answer after a slow task")
async def slow(interaction: shoal.Interaction) -> None:
    await interaction.response.defer()  # the HTTP reply says "thinking…"; the answer follows
    await asyncio.sleep(5)
    await interaction.followup.send("Done after 5 seconds.")


async def main() -> None:
    await bot.login(os.environ["DISCORD_TOKEN"])  # runs setup_hook: the commands are synced
    async with bot.endpoint(PUBLIC_KEY, host="0.0.0.0", port=PORT):  # noqa: S104 - behind your HTTPS proxy
        print(
            f"Listening on port {PORT}: set the Interactions Endpoint URL to https://<your host>/interactions"
        )
        await asyncio.Event().wait()


asyncio.run(main())
