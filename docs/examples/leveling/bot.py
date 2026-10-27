"""Leveling: experience for chatting, saved in SQLite, with /rank and /leaderboard."""

import math
import os
import random
import sqlite3
import time

import shoal
from shoal import commands

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
COOLDOWN = 60
"""Seconds between messages that earn experience, so spamming earns nothing."""


class Levels:
    """Experience per member and server, in a SQLite file."""

    def __init__(self, path: str) -> None:
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS xp"
            " (guild INTEGER, user INTEGER, xp INTEGER, PRIMARY KEY (guild, user))"
        )
        self.last_earned: dict[tuple[int, int], float] = {}

    def add(self, guild: int, user: int, amount: int) -> tuple[int, int]:
        """Add experience; return the level before and after."""
        before = self.xp(guild, user)
        self.db.execute(
            "INSERT INTO xp VALUES (?, ?, ?) ON CONFLICT (guild, user) DO UPDATE SET xp = xp + excluded.xp",
            (guild, user, amount),
        )
        self.db.commit()
        return level_of(before), level_of(before + amount)

    def xp(self, guild: int, user: int) -> int:
        row = self.db.execute("SELECT xp FROM xp WHERE guild = ? AND user = ?", (guild, user)).fetchone()
        return int(row[0]) if row else 0

    def top(self, guild: int, limit: int = 10) -> list[tuple[int, int]]:
        rows = self.db.execute(
            "SELECT user, xp FROM xp WHERE guild = ? ORDER BY xp DESC LIMIT ?", (guild, limit)
        )
        return [(int(user), int(xp)) for user, xp in rows]


def level_of(xp: int) -> int:
    """Each level takes a little more than the last: 100, 400, 900, ... experience in total."""
    return math.isqrt(xp // 100)


class Bot(commands.Bot):
    def __init__(self) -> None:
        intents = shoal.Intents.default().with_flags(message_content=True)
        super().__init__("!", intents=intents)
        self.levels = Levels("levels.db")

    async def setup_hook(self) -> None:
        if GUILD_ID:
            self.tree.copy_global_to(guild=int(GUILD_ID))
            await self.tree.sync(guild=int(GUILD_ID))
        else:
            await self.tree.sync()


bot = Bot()


@bot.event
async def on_message(message: shoal.Message) -> None:
    if message.author.bot or message.guild_id is None:
        return
    key = (int(message.guild_id), int(message.author.id))
    now = time.monotonic()
    if now - bot.levels.last_earned.get(key, 0) >= COOLDOWN:
        bot.levels.last_earned[key] = now
        before, after = bot.levels.add(*key, random.randint(15, 25))
        if after > before:
            await message.channel.send(f"🎉 {message.author.mention} reached level **{after}**!")
    await bot.process_commands(message)


@bot.hybrid_command(description="Show your level")
@commands.guild_only()
async def rank(ctx: commands.Context, member: shoal.Member | shoal.User = commands.Author) -> None:
    if ctx.guild is None:
        return
    xp = bot.levels.xp(int(ctx.guild.id), int(member.id))
    level = level_of(xp)
    needed = (level + 1) ** 2 * 100
    await ctx.send(f"**{member.display_name}**: level {level} · {xp}/{needed} XP")


@bot.hybrid_command(description="The most active members")
@commands.guild_only()
async def leaderboard(ctx: commands.Context) -> None:
    if ctx.guild is None:
        return
    lines = [
        f"**{place}.** <@{user}> · level {level_of(xp)} ({xp} XP)"
        for place, (user, xp) in enumerate(bot.levels.top(int(ctx.guild.id)), start=1)
    ]
    embed = shoal.Embed(title="Leaderboard", description="\n".join(lines) or "Nobody yet.", colour=0x5865F2)
    await ctx.send(embed=embed, allowed_mentions=shoal.AllowedMentions(users=[]))


bot.run(os.environ["DISCORD_TOKEN"])
