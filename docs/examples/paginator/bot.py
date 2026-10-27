"""A paginator: long lists split into pages with buttons, for the person who asked only."""

import os
from collections.abc import Callable

import shoal
from shoal import app_commands, ui
from shoal.client import Client

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")


class Paginator(ui.View):
    """Shows `pages` one at a time; only `owner` can turn them."""

    def __init__(self, pages: list[shoal.Embed], owner: int) -> None:
        super().__init__(timeout=120)
        self.pages, self.owner, self.index = pages, owner, 0
        self.message: shoal.Message | None = None
        self.first = self.arrow("⏮", lambda: 0)
        self.previous = self.arrow("◀", lambda: self.index - 1)
        self.counter = ui.Button(disabled=True)
        self.next = self.arrow("▶", lambda: self.index + 1)
        self.last = self.arrow("⏭", lambda: len(self.pages) - 1)
        for button in (self.first, self.previous, self.counter, self.next, self.last):
            self.add_item(button)
        self.update_buttons()

    def arrow(self, label: str, target: Callable[[], int]) -> ui.Button:
        """A button that shows the page `target()` names when pressed."""
        button = ui.Button(label=label, style=shoal.ButtonStyle.PRIMARY)

        async def turn(interaction: shoal.Interaction) -> None:
            await self.show(interaction, target())

        button.callback = turn
        return button

    def update_buttons(self) -> None:
        self.first.disabled = self.previous.disabled = self.index == 0
        self.next.disabled = self.last.disabled = self.index == len(self.pages) - 1
        self.counter.label = f"{self.index + 1}/{len(self.pages)}"

    async def show(self, interaction: shoal.Interaction, index: int) -> None:
        self.index = index
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[index], view=self)

    async def interaction_check(self, interaction: shoal.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await interaction.response.send_message("Run the command yourself to browse.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        # Grey the buttons out once nobody can use them any more.
        for button in (self.first, self.previous, self.next, self.last):
            button.disabled = True
        if self.message is not None:
            await self.message.edit(view=self)


def pages_of(title: str, lines: list[str], per_page: int = 10) -> list[shoal.Embed]:
    chunks = [lines[start : start + per_page] for start in range(0, len(lines), per_page)] or [[]]
    return [shoal.Embed(title=title, description="\n".join(chunk) or "Nothing here.") for chunk in chunks]


class Bot(Client):
    def __init__(self) -> None:
        super().__init__(intents=shoal.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        if GUILD_ID:
            self.tree.copy_global_to(guild=int(GUILD_ID))
            await self.tree.sync(guild=int(GUILD_ID))
        else:
            await self.tree.sync()


bot = Bot()


@bot.tree.command(description="Browse this server's roles")
@app_commands.guild_only()
async def roles(interaction: shoal.Interaction) -> None:
    guild = interaction.guild
    if guild is None:
        return
    ordered = sorted(guild.roles, key=lambda role: role.position, reverse=True)
    lines = [f"{role.mention} · {len(role.members)} member(s)" for role in ordered]
    view = Paginator(pages_of(f"Roles in {guild.name}", lines), interaction.user.id)
    await interaction.response.send_message(embed=view.pages[0], view=view)
    view.message = await interaction.original_response()


@bot.tree.command(description="Browse numbers, as an example of many pages")
async def numbers(interaction: shoal.Interaction) -> None:
    view = Paginator(pages_of("Squares", [f"{n}² = {n * n}" for n in range(1, 101)]), interaction.user.id)
    await interaction.response.send_message(embed=view.pages[0], view=view)
    view.message = await interaction.original_response()


bot.run(os.environ["DISCORD_TOKEN"])
