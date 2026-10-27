"""Support tickets: a button opens a form, the bot creates a private channel, staff close it."""

import asyncio
import os

import shoal
from shoal import app_commands, ui
from shoal.client import Client
from shoal.core.snowflake import Snowflake
from shoal.payloads import OverwriteType, PartialOverwrite, TextInputStyle

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
CATEGORY = "Tickets"
STAFF_ROLE = os.environ.get("STAFF_ROLE", "Staff")
"""Members with this role see every ticket."""

TALK = shoal.Permissions(view_channel=True, send_messages=True, read_message_history=True, attach_files=True)


def hidden_from_everyone(guild: shoal.Guild) -> PartialOverwrite:
    # The @everyone role has the guild's ID.
    return PartialOverwrite(
        id=Snowflake(guild.id), type=OverwriteType.ROLE, deny=shoal.Permissions(view_channel=True)
    )


def can_talk(target: shoal.Role | shoal.Member) -> PartialOverwrite:
    kind = OverwriteType.ROLE if isinstance(target, shoal.Role) else OverwriteType.MEMBER
    return PartialOverwrite(id=Snowflake(target.id), type=kind, allow=TALK)


class TicketForm(ui.Modal, title="Open a ticket"):
    topic = ui.TextInput(label="What do you need help with?", max_length=100)
    details = ui.TextInput(label="Details", style=TextInputStyle.PARAGRAPH, required=False)

    async def on_submit(self, interaction: shoal.Interaction) -> None:
        guild, member = interaction.guild, interaction.user
        if guild is None or not isinstance(member, shoal.Member) or guild.me is None:
            return
        await interaction.response.defer(ephemeral=True)
        category = next((c for c in guild.categories if c.name == CATEGORY), None)
        if category is None:
            category = await guild.create_category(CATEGORY, overwrites=[hidden_from_everyone(guild)])
        overwrites = [hidden_from_everyone(guild), can_talk(member), can_talk(guild.me)]
        staff = next((role for role in guild.roles if role.name == STAFF_ROLE), None)
        if staff is not None:
            overwrites.append(can_talk(staff))
        channel = await guild.create_text_channel(
            f"ticket-{member.name}", category=category, topic=str(self.topic), overwrites=overwrites
        )
        embed = shoal.Embed(
            title=str(self.topic), description=str(self.details) or "No details.", colour=0x5865F2
        )
        await channel.send(
            f"{member.mention}, staff will be with you soon.", embed=embed, view=TicketControls()
        )
        await interaction.followup.send(f"Your ticket: {channel.mention}", ephemeral=True)


class TicketPanel(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(label="Open a ticket", emoji="🎫", style=shoal.ButtonStyle.PRIMARY, custom_id="tickets:open")
    async def open(self, interaction: shoal.Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(TicketForm())


class TicketControls(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(label="Close", emoji="🔒", style=shoal.ButtonStyle.DANGER, custom_id="tickets:close")
    async def close(self, interaction: shoal.Interaction, button: ui.Button) -> None:
        channel = interaction.channel
        if not isinstance(channel, shoal.TextChannel):
            return
        await interaction.response.send_message(
            f"Closed by {interaction.user.mention}; deleting in 5 seconds."
        )
        await asyncio.sleep(5)
        await channel.delete(reason=f"Ticket closed by {interaction.user}")


class Bot(Client):
    def __init__(self) -> None:
        super().__init__(intents=shoal.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self.add_view(TicketPanel())
        self.add_view(TicketControls())
        if GUILD_ID:
            self.tree.copy_global_to(guild=int(GUILD_ID))
            await self.tree.sync(guild=int(GUILD_ID))
        else:
            await self.tree.sync()


bot = Bot()


@bot.tree.command(description="Post the ticket panel in this channel")
@app_commands.default_permissions(manage_channels=True)
@app_commands.guild_only()
async def ticketpanel(interaction: shoal.Interaction) -> None:
    embed = shoal.Embed(title="Need help?", description="Press the button to open a private ticket.")
    await interaction.response.send_message(embed=embed, view=TicketPanel())


bot.run(os.environ["DISCORD_TOKEN"])
