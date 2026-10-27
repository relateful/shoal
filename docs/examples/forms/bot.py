"""Forms: a modal with a text input, radio buttons, checkboxes, a select and a file upload."""

import os

import shoal
from shoal import app_commands, ui
from shoal.client import Client
from shoal.payloads import CheckboxGroupOption, RadioGroupOption, SelectOption, TextInputStyle

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
APPLICATIONS = "applications"
"""Submitted applications are posted in a channel with this name, if there is one."""


class StaffApplication(ui.Modal, title="Staff application"):
    def __init__(self) -> None:
        super().__init__()
        self.intro = ui.TextInput(style=TextInputStyle.PARAGRAPH, max_length=500)
        self.team = ui.RadioGroup(
            options=[
                RadioGroupOption(value="mod", label="Moderation"),
                RadioGroupOption(value="events", label="Events"),
                RadioGroupOption(value="support", label="Support"),
            ]
        )
        self.days = ui.CheckboxGroup(
            options=[CheckboxGroupOption(value=day, label=day) for day in ("Weekdays", "Saturday", "Sunday")],
            required=False,
        )
        self.timezone = ui.Select(
            options=[
                SelectOption(label=f"UTC{offset:+d}", value=str(offset)) for offset in range(-11, 13, 2)
            ],
            placeholder="Your time zone",
        )
        self.examples = ui.FileUpload(file_types=["image"], max_values=3, required=False)
        # A modal holds at most five items; Shoal refuses a sixth when it is added.
        self.add_item(ui.Label("About you", self.intro, description="Why do you want to help?"))
        self.add_item(ui.Label("Team", self.team))
        self.add_item(ui.Label("When are you around?", self.days))
        self.add_item(ui.Label("Time zone", self.timezone))
        self.add_item(ui.Label("Screenshots of past work", self.examples))

    async def on_submit(self, interaction: shoal.Interaction) -> None:
        embed = shoal.Embed(
            title=f"Application: {interaction.user.display_name}", description=str(self.intro)
        )
        embed.add_field(name="Team", value=self.team.value or "?")
        embed.add_field(name="Available", value=", ".join(self.days.values) or "Not said")
        embed.add_field(name="Time zone", value=f"UTC{int(self.timezone.values[0]):+d}")
        if self.examples.values:
            embed.set_image(url=self.examples.values[0].url)
        guild = interaction.guild
        channel = next((c for c in guild.text_channels if c.name == APPLICATIONS), None) if guild else None
        if channel is not None:
            await channel.send(embed=embed)
        await interaction.response.send_message("Thanks! We'll get back to you.", embed=embed, ephemeral=True)


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


@bot.tree.command(description="Apply to join the staff team")
async def apply(interaction: shoal.Interaction) -> None:
    await interaction.response.send_modal(StaffApplication())


bot.run(os.environ["DISCORD_TOKEN"])
