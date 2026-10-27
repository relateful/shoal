"""Polls: Discord's native polls, and a button vote whose tally updates live."""

import os
from collections import Counter

import shoal
from shoal import app_commands, ui
from shoal.app_commands import Range
from shoal.client import Client
from shoal.payloads import PollAnswer, PollCreateRequest, PollMedia
from shoal.payloads.gateway_events import MessagePollVoteAdd

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")


class Bot(Client):
    def __init__(self) -> None:
        # Poll votes arrive with the Guild Message Polls intent, part of the defaults.
        super().__init__(intents=shoal.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        if GUILD_ID:
            self.tree.copy_global_to(guild=int(GUILD_ID))
            await self.tree.sync(guild=int(GUILD_ID))
        else:
            await self.tree.sync()


bot = Bot()


@bot.tree.command(description="Start a Discord poll")
@app_commands.describe(answers="Answers separated by commas (up to 10)", hours="How long it runs")
async def poll(
    interaction: shoal.Interaction,
    question: Range[str, 1, 300],
    answers: str,
    hours: Range[int, 1, 768] = 24,
    multiple: bool = False,
) -> None:
    choices = [answer.strip()[:55] for answer in answers.split(",") if answer.strip()][:10]
    if len(choices) < 2:
        await interaction.response.send_message("Give at least two answers.", ephemeral=True)
        return
    request = PollCreateRequest(
        question=PollMedia(text=question),
        answers=[PollAnswer(poll_media=PollMedia(text=choice)) for choice in choices],
        duration=hours,
        allow_multiselect=multiple,
    )
    await interaction.response.send_message(poll=request)


@bot.event
async def on_raw_poll_vote_add(vote: MessagePollVoteAdd) -> None:
    print(f"user {vote.user_id} voted for answer {vote.answer_id} on message {vote.message_id}")


class QuickVote(ui.View):
    """A yes/no vote; each member has one vote and can change it."""

    def __init__(self, question: str) -> None:
        super().__init__(timeout=3600)
        self.question = question
        self.votes: dict[int, str] = {}

    def summary(self) -> str:
        tally = Counter(self.votes.values())
        return f"**{self.question}**\n👍 {tally['yes']} · 👎 {tally['no']}"

    async def record(self, interaction: shoal.Interaction, choice: str) -> None:
        self.votes[interaction.user.id] = choice
        await interaction.response.edit_message(content=self.summary(), view=self)

    @ui.button(label="Yes", emoji="👍", style=shoal.ButtonStyle.SUCCESS)
    async def yes(self, interaction: shoal.Interaction, button: ui.Button) -> None:
        await self.record(interaction, "yes")

    @ui.button(label="No", emoji="👎", style=shoal.ButtonStyle.DANGER)
    async def no(self, interaction: shoal.Interaction, button: ui.Button) -> None:
        await self.record(interaction, "no")


@bot.tree.command(description="A quick yes/no vote with a live tally")
async def vote(interaction: shoal.Interaction, question: Range[str, 1, 200]) -> None:
    view = QuickVote(question)
    await interaction.response.send_message(view.summary(), view=view)


bot.run(os.environ["DISCORD_TOKEN"])
