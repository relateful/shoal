"""Reminders: /remind in 10m to stretch, delivered on time even across restarts."""

import asyncio
import contextlib
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import msgspec

import shoal
from shoal import app_commands
from shoal.app_commands import Choice
from shoal.client import Client
from shoal.rest.errors import HTTPError

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
SAVED = Path("reminders.json")
log = logging.getLogger("reminders")
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86_400, "w": 604_800}


@dataclass
class Reminder:
    id: int
    user_id: int
    channel_id: int
    text: str
    due: float


def parse_duration(text: str) -> int | None:
    """Seconds in `1h30m`, `10m`, `2d`; `None` if it is not a duration."""
    parts = re.findall(r"(\d+)\s*([smhdw])", text.lower())
    if not parts or "".join(number + unit for number, unit in parts) != re.sub(r"\s", "", text.lower()):
        return None
    return sum(int(number) * UNITS[unit] for number, unit in parts)


class Bot(Client):
    def __init__(self) -> None:
        super().__init__(intents=shoal.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.reminders = (
            msgspec.json.decode(SAVED.read_bytes(), type=list[Reminder]) if SAVED.exists() else []
        )
        self.wake = asyncio.Event()
        self.delivery: asyncio.Task[None] | None = None

    async def setup_hook(self) -> None:
        self.delivery = asyncio.create_task(self.deliver())
        if GUILD_ID:
            self.tree.copy_global_to(guild=int(GUILD_ID))
            await self.tree.sync(guild=int(GUILD_ID))
        else:
            await self.tree.sync()

    def save(self) -> None:
        SAVED.write_bytes(msgspec.json.encode(self.reminders))

    def add(self, reminder: Reminder) -> None:
        self.reminders.append(reminder)
        self.save()
        self.wake.set()  # the new one may be due before the one the loop waits for

    async def deliver(self) -> None:
        """Sleep until the next reminder is due, send it, repeat; wake early when one is added."""
        await self.wait_until_ready()
        while True:
            self.wake.clear()
            upcoming = min(self.reminders, key=lambda reminder: reminder.due, default=None)
            delay = upcoming.due - time.time() if upcoming is not None else 3600
            if delay > 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.wake.wait(), timeout=delay)
                continue
            if upcoming is not None:
                self.reminders.remove(upcoming)
                self.save()
                channel = self.get_partial_messageable(upcoming.channel_id)
                try:
                    await channel.send(
                        f"⏰ <@{upcoming.user_id}>, you asked me to remind you: {upcoming.text}"
                    )
                except HTTPError:  # the channel is gone, or the bot can no longer write there
                    log.exception("could not deliver reminder %d", upcoming.id)


bot = Bot()


@bot.tree.command(description="Remind you of something later")
@app_commands.describe(when="How long from now: 10m, 1h30m, 2d", what="What to remind you of")
async def remind(interaction: shoal.Interaction, when: str, what: str) -> None:
    seconds = parse_duration(when)
    if seconds is None or not 0 < seconds <= 365 * 86_400:
        await interaction.response.send_message("Use a duration like `10m`, `1h30m` or `2d`.", ephemeral=True)
        return
    due = time.time() + seconds
    reminder = Reminder(
        int(interaction.id), int(interaction.user.id), int(interaction.channel_id or 0), what, due
    )
    bot.add(reminder)
    await interaction.response.send_message(f"I'll remind you <t:{int(due)}:R>.", ephemeral=True)


@bot.tree.command(description="List your reminders")
async def reminders(interaction: shoal.Interaction) -> None:
    mine = sorted((r for r in bot.reminders if r.user_id == interaction.user.id), key=lambda r: r.due)
    lines = [f"<t:{int(r.due)}:R> · {r.text}" for r in mine] or ["No reminders."]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(description="Cancel one of your reminders")
async def forget(interaction: shoal.Interaction, reminder: str) -> None:
    found = next(
        (r for r in bot.reminders if str(r.id) == reminder and r.user_id == interaction.user.id), None
    )
    if found is None:
        await interaction.response.send_message("No such reminder.", ephemeral=True)
        return
    bot.reminders.remove(found)
    bot.save()
    await interaction.response.send_message(f"Forgot: {found.text}", ephemeral=True)


@forget.autocomplete("reminder")
async def your_reminders(interaction: shoal.Interaction, current: str) -> list[Choice[str]]:
    mine = [
        r for r in bot.reminders if r.user_id == interaction.user.id and current.lower() in r.text.lower()
    ]
    return [Choice(name=r.text[:100], value=str(r.id)) for r in mine][:25]


bot.run(os.environ["DISCORD_TOKEN"])
