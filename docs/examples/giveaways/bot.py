"""Giveaways: enter with a button, winners drawn when the timer ends, even after a restart."""

import asyncio
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import msgspec

import shoal
from shoal import app_commands, ui
from shoal.app_commands import Range
from shoal.client import Client

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
SAVED = Path("giveaways.json")


@dataclass
class Giveaway:
    channel_id: int
    message_id: int
    prize: str
    winners: int
    ends_at: float
    entrants: list[int] = field(default_factory=list[int])


class Giveaways:
    """Running giveaways, saved to a file so a restart loses nothing."""

    def __init__(self) -> None:
        loaded = msgspec.json.decode(SAVED.read_bytes(), type=list[Giveaway]) if SAVED.exists() else []
        self.running: dict[int, Giveaway] = {giveaway.message_id: giveaway for giveaway in loaded}

    def save(self) -> None:
        SAVED.write_bytes(msgspec.json.encode(list(self.running.values())))


class EnterButton(ui.View):
    def __init__(self, giveaways: Giveaways) -> None:
        super().__init__(timeout=None)
        self.giveaways = giveaways

    @ui.button(label="Enter", emoji="🎉", style=shoal.ButtonStyle.SUCCESS, custom_id="giveaway:enter")
    async def enter(self, interaction: shoal.Interaction, button: ui.Button) -> None:
        message = interaction.message
        giveaway = self.giveaways.running.get(message.id) if message is not None else None
        if giveaway is None:
            await interaction.response.send_message("This giveaway has ended.", ephemeral=True)
        elif interaction.user.id in giveaway.entrants:
            giveaway.entrants.remove(int(interaction.user.id))
            self.giveaways.save()
            await interaction.response.send_message("You left the giveaway.", ephemeral=True)
        else:
            giveaway.entrants.append(int(interaction.user.id))
            self.giveaways.save()
            await interaction.response.send_message("You're in! Press again to leave.", ephemeral=True)


class Bot(Client):
    def __init__(self) -> None:
        super().__init__(intents=shoal.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.giveaways = Giveaways()
        self.timers: set[asyncio.Task[None]] = set()

    async def setup_hook(self) -> None:
        self.add_view(EnterButton(self.giveaways))
        for giveaway in self.giveaways.running.values():
            self.schedule(giveaway)
        if GUILD_ID:
            self.tree.copy_global_to(guild=int(GUILD_ID))
            await self.tree.sync(guild=int(GUILD_ID))
        else:
            await self.tree.sync()

    def schedule(self, giveaway: Giveaway) -> None:
        # Keep a reference: the event loop only holds tasks weakly.
        timer = asyncio.create_task(self.finish_later(giveaway))
        self.timers.add(timer)
        timer.add_done_callback(self.timers.discard)

    async def finish_later(self, giveaway: Giveaway) -> None:
        await asyncio.sleep(max(giveaway.ends_at - time.time(), 0))
        self.giveaways.running.pop(giveaway.message_id, None)
        self.giveaways.save()
        winners = random.sample(giveaway.entrants, min(giveaway.winners, len(giveaway.entrants)))
        channel = self.get_partial_messageable(giveaway.channel_id)
        message = channel.get_partial_message(giveaway.message_id)
        result = ", ".join(f"<@{winner}>" for winner in winners) or "nobody entered"
        await message.edit(embed=announcement(giveaway, f"Winner(s): {result}"), view=None)
        if winners:
            await channel.send(f"🎉 Congratulations {result}, you won **{giveaway.prize}**!")


def announcement(giveaway: Giveaway, status: str) -> shoal.Embed:
    return shoal.Embed(title=f"🎁 {giveaway.prize}", description=status, colour=0xF1C40F)


bot = Bot()


@bot.tree.command(description="Start a giveaway in this channel")
@app_commands.default_permissions(manage_guild=True)
@app_commands.guild_only()
@app_commands.describe(minutes="How long it runs", winners="How many win")
async def giveaway(
    interaction: shoal.Interaction, prize: str, minutes: Range[int, 1, 10_080], winners: Range[int, 1, 20] = 1
) -> None:
    channel = interaction.channel
    if not isinstance(channel, shoal.TextChannel):
        return
    ends_at = time.time() + minutes * 60
    # Plain ints: msgspec saves `int`, not `Snowflake`, the int subclass IDs arrive as.
    entry = Giveaway(int(channel.id), 0, prize, winners, ends_at)
    status = f"Ends <t:{int(ends_at)}:R> · {winners} winner(s)"
    message = await channel.send(embed=announcement(entry, status), view=EnterButton(bot.giveaways))
    entry.message_id = int(message.id)
    bot.giveaways.running[message.id] = entry
    bot.giveaways.save()
    bot.schedule(entry)
    await interaction.response.send_message("Giveaway started!", ephemeral=True)


bot.run(os.environ["DISCORD_TOKEN"])
