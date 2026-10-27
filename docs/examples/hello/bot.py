"""The smallest bot: answer "ping" with "pong"."""

import os

import shoal
from shoal.client import Client

intents = shoal.Intents.default().with_flags(message_content=True)
client = Client(intents=intents)


@client.event
async def on_ready() -> None:
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message: shoal.Message) -> None:
    if message.author.bot:
        return
    if message.content == "ping":
        await message.reply("pong")


client.run(os.environ["DISCORD_TOKEN"])
