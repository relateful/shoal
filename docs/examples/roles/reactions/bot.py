"""Reaction roles: react to a message to get a role, remove the reaction to lose it."""

import os
from pathlib import Path

import msgspec

import shoal
from shoal import commands
from shoal.payloads.gateway_events import MessageReactionAdd, MessageReactionRemove

ROLES = {"🔴": "Red", "🟢": "Green", "🔵": "Blue"}
"""Each emoji and the role it gives; missing roles are created by !reactionroles."""

SAVED = Path("reaction_roles.json")
"""The messages that hand out roles, kept across restarts."""

intents = shoal.Intents.default().with_flags(message_content=True)
bot = commands.Bot("!", intents=intents)
menus: set[int] = msgspec.json.decode(SAVED.read_bytes(), type=set[int]) if SAVED.exists() else set()


def save_menus() -> None:
    SAVED.write_bytes(msgspec.json.encode(sorted(menus)))


@bot.command()
@commands.guild_only()
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True, add_reactions=True)
async def reactionroles(ctx: commands.Context) -> None:
    """Post a reaction role menu here, creating its roles if needed."""
    guild = ctx.guild
    if guild is None:
        return
    existing = {role.name for role in guild.roles}
    for name in ROLES.values():
        if name not in existing:
            await guild.create_role(name=name, reason=f"Reaction roles, set up by {ctx.author}")
    lines = [f"{emoji} → **{name}**" for emoji, name in ROLES.items()]
    menu = await ctx.send(embed=shoal.Embed(title="Pick your colours", description="\n".join(lines)))
    for emoji in ROLES:
        await menu.add_reaction(emoji)
    menus.add(int(menu.id))  # a plain int, which msgspec saves
    save_menus()


def role_for(event: MessageReactionAdd | MessageReactionRemove) -> tuple[shoal.Guild, shoal.Role] | None:
    """The guild and role a reaction is about, when it is on a menu."""
    # `guild_id` is left out (UNSET) for a reaction in a DM.
    if event.message_id not in menus or event.emoji.name not in ROLES or not isinstance(event.guild_id, int):
        return None
    guild = bot.get_guild(event.guild_id)
    if guild is None:
        return None
    role = next((role for role in guild.roles if role.name == ROLES[event.emoji.name]), None)
    return (guild, role) if role is not None else None


@bot.event
async def on_raw_reaction_add(event: MessageReactionAdd) -> None:
    found = role_for(event)
    if found is None or (bot.user is not None and event.user_id == bot.user.id):
        return
    guild, role = found
    member = await guild.fetch_member(event.user_id)
    await member.add_roles(role, reason="Reaction role")


@bot.event
async def on_raw_reaction_remove(event: MessageReactionRemove) -> None:
    found = role_for(event)
    if found is None:
        return
    guild, role = found
    member = await guild.fetch_member(event.user_id)
    await member.remove_roles(role, reason="Reaction role removed")


bot.run(os.environ["DISCORD_TOKEN"])
