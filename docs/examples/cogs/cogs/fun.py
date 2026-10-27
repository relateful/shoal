"""Games: a cog with hybrid commands and a listener."""

import random

import shoal
from shoal import commands

ANSWERS = ["Yes.", "No.", "Maybe.", "Ask again later.", "Definitely.", "Not a chance."]


class Fun(commands.Cog):
    """Games and dice."""

    def __init__(self) -> None:
        self.greeted: set[int] = set()

    @commands.hybrid_command(name="8ball", description="Ask the magic 8-ball")
    async def eight_ball(self, ctx: commands.Context, *, question: str) -> None:
        await ctx.send(f"> {question}\n{random.choice(ANSWERS)}")

    @commands.hybrid_command(description="Roll a die")
    async def dice(self, ctx: commands.Context, sides: commands.Range[int, 2, 1000] = 6) -> None:
        await ctx.send(f"🎲 {random.randint(1, sides)}")

    @commands.Cog.listener()
    async def on_message(self, message: shoal.Message) -> None:
        # Say hi the first time someone says hello, once per run.
        if (
            not message.author.bot
            and message.content.lower() == "hello"
            and message.author.id not in self.greeted
        ):
            self.greeted.add(message.author.id)
            await message.add_reaction("👋")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fun())
