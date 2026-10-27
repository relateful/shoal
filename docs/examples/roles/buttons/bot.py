"""Self-assignable roles with buttons and a select menu that keep working after a restart."""

import os

import shoal
from shoal import app_commands, ui
from shoal.client import Client
from shoal.payloads import SelectOption

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
ROLES = {"Announcements": "📣", "Events": "🎉", "Giveaways": "🎁"}
"""Ping roles members toggle with a button; missing ones are created by /rolemenu."""

PRONOUNS = ["he/him", "she/her", "they/them", "any pronouns"]
"""Roles picked from a select: choosing replaces the previous choice."""


def role_named(guild: shoal.Guild, name: str) -> shoal.Role | None:
    return next((role for role in guild.roles if role.name == name), None)


class RoleButton(ui.Button):
    def __init__(self, name: str, emoji: str) -> None:
        # A fixed custom_id lets the view answer clicks on messages sent before a restart.
        super().__init__(
            label=name, emoji=emoji, custom_id=f"roles:toggle:{name}", style=shoal.ButtonStyle.SECONDARY
        )
        self.role_name = name

    async def callback(self, interaction: shoal.Interaction) -> None:
        member, guild = interaction.user, interaction.guild
        role = role_named(guild, self.role_name) if guild is not None else None
        if role is None or not isinstance(member, shoal.Member):
            await interaction.response.send_message("That role is gone; ask an admin.", ephemeral=True)
            return
        if member.has_role(role.id):
            await member.remove_roles(role, reason="Role menu")
            await interaction.response.send_message(f"Removed {role.mention}.", ephemeral=True)
        else:
            await member.add_roles(role, reason="Role menu")
            await interaction.response.send_message(f"Added {role.mention}.", ephemeral=True)


class RoleMenu(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        for name, emoji in ROLES.items():
            self.add_item(RoleButton(name, emoji))

    @ui.select(
        custom_id="roles:pronouns",
        placeholder="Your pronouns",
        min_values=0,
        max_values=len(PRONOUNS),
        options=[SelectOption(label=name, value=name) for name in PRONOUNS],
    )
    async def pronouns(self, interaction: shoal.Interaction, select: ui.Select) -> None:
        member, guild = interaction.user, interaction.guild
        if guild is None or not isinstance(member, shoal.Member):
            return
        chosen = [role for name in select.values if (role := role_named(guild, name)) is not None]
        dropped = [
            role for name in PRONOUNS if (role := role_named(guild, name)) is not None and role not in chosen
        ]
        await member.remove_roles(*dropped, reason="Role menu")
        await member.add_roles(*chosen, reason="Role menu")
        await interaction.response.send_message(
            f"Pronouns set to {', '.join(select.values) or 'none'}.", ephemeral=True
        )


class Bot(Client):
    def __init__(self) -> None:
        super().__init__(intents=shoal.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self.add_view(RoleMenu())  # answers the buttons of every menu ever posted
        if GUILD_ID:
            self.tree.copy_global_to(guild=int(GUILD_ID))
            await self.tree.sync(guild=int(GUILD_ID))
        else:
            await self.tree.sync()


bot = Bot()


@bot.tree.command(description="Post the role menu in this channel")
@app_commands.default_permissions(manage_roles=True)
@app_commands.guild_only()
async def rolemenu(interaction: shoal.Interaction) -> None:
    guild, channel = interaction.guild, interaction.channel
    if guild is None or not isinstance(channel, shoal.TextChannel):
        return
    await interaction.response.defer(ephemeral=True)
    for name in [*ROLES, *PRONOUNS]:
        if role_named(guild, name) is None:
            await guild.create_role(name=name, mentionable=False, reason="Role menu")
    await channel.send(embed=shoal.Embed(title="Pick your roles", colour=0x5865F2), view=RoleMenu())
    await interaction.followup.send("Menu posted.", ephemeral=True)


bot.run(os.environ["DISCORD_TOKEN"])
