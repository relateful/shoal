"""Welcome new members with a message and a role, and say goodbye when they leave."""

import os

import shoal
from shoal.client import Client
from shoal.payloads.gateway_events import GuildMemberRemove

AUTOROLE = os.environ.get("AUTOROLE", "Member")
"""The role every new member gets; leave it empty for none."""

intents = shoal.Intents.default().with_flags(guild_members=True)
client = Client(intents=intents)


def welcome_channel(guild: shoal.Guild) -> shoal.TextChannel | None:
    """The server's system channel, or a channel named #welcome."""
    return guild.system_channel or next((c for c in guild.text_channels if c.name == "welcome"), None)


@client.event
async def on_member_join(member: shoal.Member) -> None:
    guild = member.guild
    if guild is None:
        return
    channel = welcome_channel(guild)
    if channel is not None:
        embed = shoal.Embed(
            title=f"Welcome to {guild.name}!",
            description=f"Hi {member.mention}, you are member #{guild.member_count}.",
            colour=0x57F287,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(
            member.mention, embed=embed, allowed_mentions=shoal.AllowedMentions(users=[member.id])
        )
    role = next((role for role in guild.roles if role.name == AUTOROLE), None)
    if role is not None and not member.bot:
        await member.add_roles(role, reason="Autorole")


@client.event
async def on_raw_member_remove(event: GuildMemberRemove) -> None:
    # The raw event fires even when the member was not cached, with the user who left.
    guild = client.get_guild(event.guild_id)
    channel = welcome_channel(guild) if guild is not None else None
    if channel is not None:
        await channel.send(f"**{event.user.username}** left. 👋")


client.run(os.environ["DISCORD_TOKEN"])
