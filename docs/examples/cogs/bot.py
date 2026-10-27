"""A bot split into cogs, loaded as extensions and reloadable without a restart."""

import os
from pathlib import Path

import shoal
from shoal import commands

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
EXTENSIONS = [f"cogs.{path.stem}" for path in sorted(Path(__file__).with_name("cogs").glob("*.py"))]


class Bot(commands.Bot):
    def __init__(self) -> None:
        intents = shoal.Intents.default().with_flags(message_content=True)
        super().__init__("!", intents=intents)

    async def setup_hook(self) -> None:
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        if GUILD_ID:
            self.tree.copy_global_to(guild=int(GUILD_ID))
            await self.tree.sync(guild=int(GUILD_ID))
        else:
            await self.tree.sync()


Bot().run(os.environ["DISCORD_TOKEN"])
