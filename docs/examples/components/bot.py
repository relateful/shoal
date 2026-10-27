"""Components V2: messages laid out with containers, sections, images and buttons."""

import os
from datetime import UTC, datetime

import shoal
from shoal import app_commands, ui
from shoal.client import Client
from shoal.payloads import SeparatorSpacing

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
DOCS = "https://github.com/relateful/shoal"


class ServerCard(ui.LayoutView):
    """A server's details; Refresh redraws it with fresh numbers."""

    def __init__(self, guild: shoal.Guild) -> None:
        super().__init__(timeout=600)
        self.guild = guild
        self.draw()

    def draw(self) -> None:
        guild = self.guild
        self.clear_items()
        heading = f"## {guild.name}\n{guild.description or 'No description.'}"
        header = (
            ui.Section(heading, accessory=ui.Thumbnail(guild.icon.url))
            if guild.icon
            else ui.TextDisplay(heading)
        )
        stats = (
            f"**Members** {guild.member_count or '?'} · **Channels** {len(guild.channels)} · "
            f"**Roles** {len(guild.roles)}\n**Created** <t:{int(guild.created_at.timestamp())}:D>"
        )
        refresh = ui.Button(label="Refresh", style=shoal.ButtonStyle.PRIMARY)
        refresh.callback = self.refresh
        card = ui.Container(
            header,
            ui.Separator(),
            ui.TextDisplay(stats),
            ui.TextDisplay(f"-# Updated <t:{int(datetime.now(UTC).timestamp())}:R>"),
            ui.ActionRow(refresh, ui.Button(label="Shoal on GitHub", url=DOCS)),
            accent_colour=0x5865F2,
        )
        self.add_item(card)
        if guild.banner:
            self.add_item(ui.MediaGallery(guild.banner.url))

    async def refresh(self, interaction: shoal.Interaction) -> None:
        self.draw()
        await interaction.response.edit_message(view=self)


class ReleaseNotes(ui.LayoutView):
    """A fixed layout declared on the class, like a form: items are copied for each message."""

    title = ui.TextDisplay("# Release notes")
    body = ui.Container(
        ui.TextDisplay("### New\n- Components V2 layouts\n- Polls\n- Voice messages"),
        ui.Separator(spacing=SeparatorSpacing.LARGE),
        ui.TextDisplay("### Fixed\n- Everything you reported, probably"),
        accent_colour=0x57F287,
    )
    actions = ui.ActionRow()

    @actions.button(label="I read it", style=shoal.ButtonStyle.SUCCESS)
    async def read(self, interaction: shoal.Interaction, button: ui.Button) -> None:
        await interaction.response.send_message("Thanks for reading! ✅", ephemeral=True)


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


@bot.tree.command(description="Show this server's card")
@app_commands.guild_only()
async def server(interaction: shoal.Interaction) -> None:
    if interaction.guild is not None:
        await interaction.response.send_message(view=ServerCard(interaction.guild))


@bot.tree.command(description="Post the release notes")
async def notes(interaction: shoal.Interaction) -> None:
    await interaction.response.send_message(view=ReleaseNotes())


bot.run(os.environ["DISCORD_TOKEN"])
