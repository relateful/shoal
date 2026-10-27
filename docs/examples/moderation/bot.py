"""Moderation slash commands with permission checks, reasons in the audit log, and a mod log."""

import os
from datetime import timedelta

import shoal
from shoal import app_commands
from shoal.app_commands import Range
from shoal.client import Client

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
MOD_LOG = "mod-log"
"""Actions are recorded in a channel with this name, if the server has one."""


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


async def log_action(interaction: shoal.Interaction, action: str, target: shoal.Member, reason: str) -> None:
    """Answer the moderator, and record the action in #mod-log."""
    await interaction.response.send_message(f"{action} {target.mention}: {reason}", ephemeral=True)
    guild = interaction.guild
    channel = next((c for c in guild.text_channels if c.name == MOD_LOG), None) if guild is not None else None
    if channel is not None:
        embed = shoal.Embed(title=action, colour=0xED4245, description=f"{target.mention} ({target.id})")
        embed.add_field(name="Moderator", value=interaction.user.mention)
        embed.add_field(name="Reason", value=reason)
        await channel.send(embed=embed)


def rank(member: shoal.Member) -> int:
    """How high a member's top role sits; 0 with no role."""
    return member.top_role.position if member.top_role is not None else 0


async def can_act(interaction: shoal.Interaction, target: shoal.Member) -> bool:
    """Refuse to act on yourself, the owner, or someone whose top role is not below yours."""
    moderator, guild = interaction.user, interaction.guild
    if guild is None or not isinstance(moderator, shoal.Member):
        return False
    if target.id in (moderator.id, guild.owner_id):
        await interaction.response.send_message("You can't do that to them.", ephemeral=True)
        return False
    if moderator.id != guild.owner_id and rank(target) >= rank(moderator):
        await interaction.response.send_message("Their top role is not below yours.", ephemeral=True)
        return False
    return True


@bot.tree.command(description="Time a member out")
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.bot_has_permissions(moderate_members=True)
@app_commands.guild_only()
async def timeout(
    interaction: shoal.Interaction,
    member: shoal.Member,
    minutes: Range[int, 1, 40320],
    reason: str = "No reason",
) -> None:
    if await can_act(interaction, member):
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        await log_action(interaction, f"Timed out for {minutes} min", member, reason)


@bot.tree.command(description="Lift a member's timeout")
@app_commands.default_permissions(moderate_members=True)
@app_commands.guild_only()
async def untimeout(interaction: shoal.Interaction, member: shoal.Member) -> None:
    await member.timeout(None, reason=f"Lifted by {interaction.user}")
    await log_action(interaction, "Timeout lifted", member, "—")


@bot.tree.command(description="Kick a member")
@app_commands.default_permissions(kick_members=True)
@app_commands.checks.bot_has_permissions(kick_members=True)
@app_commands.guild_only()
async def kick(interaction: shoal.Interaction, member: shoal.Member, reason: str = "No reason") -> None:
    if await can_act(interaction, member):
        await member.kick(reason=reason)
        await log_action(interaction, "Kicked", member, reason)


@bot.tree.command(description="Ban a member")
@app_commands.default_permissions(ban_members=True)
@app_commands.checks.bot_has_permissions(ban_members=True)
@app_commands.guild_only()
@app_commands.describe(delete_days="Delete their messages from the last few days")
async def ban(
    interaction: shoal.Interaction,
    member: shoal.Member,
    reason: str = "No reason",
    delete_days: Range[int, 0, 7] = 0,
) -> None:
    if await can_act(interaction, member):
        await member.ban(reason=reason, delete_message_seconds=delete_days * 86_400)
        await log_action(interaction, "Banned", member, reason)


@bot.tree.command(description="Delete recent messages in this channel")
@app_commands.default_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
@app_commands.checks.cooldown(1, 5.0)
@app_commands.guild_only()
async def purge(
    interaction: shoal.Interaction, amount: Range[int, 1, 100], user: shoal.Member | None = None
) -> None:
    channel = interaction.channel
    if not isinstance(channel, shoal.TextChannel):
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await channel.purge(
        limit=amount,
        check=lambda message: user is None or message.author.id == user.id,
        reason=f"By {interaction.user}",
    )
    await interaction.followup.send(f"Deleted {len(deleted)} message(s).", ephemeral=True)


@bot.tree.error
async def on_app_command_error(interaction: shoal.Interaction, error: Exception) -> None:
    if isinstance(error, app_commands.BotMissingPermissionsError):
        message = f"I need: {', '.join(error.missing_permissions)}."
    elif isinstance(error, app_commands.CommandOnCooldownError):
        message = f"Try again in {error.retry_after:.0f}s."
    else:
        raise error
    await interaction.response.send_message(message, ephemeral=True)


bot.run(os.environ["DISCORD_TOKEN"])
