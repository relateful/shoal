"""Server logs: edited and deleted messages, joins, leaves, nickname and role changes."""

import os
from datetime import UTC, datetime

import shoal
from shoal.client import Client

LOG_CHANNEL = "logs"

intents = shoal.Intents.default().with_flags(message_content=True, guild_members=True)
client = Client(intents=intents)


async def log(guild: shoal.Guild | None, title: str, description: str, colour: int) -> None:
    channel = next((c for c in guild.text_channels if c.name == LOG_CHANNEL), None) if guild else None
    if channel is not None:
        embed = shoal.Embed(title=title, description=description, colour=colour, timestamp=datetime.now(UTC))
        await channel.send(embed=embed, allowed_mentions=shoal.AllowedMentions(users=[], roles=[]))


@client.event
async def on_message_edit(before: shoal.Message, after: shoal.Message) -> None:
    # Fires only for messages in the cache: their old content is known.
    if after.author.bot or before.content == after.content:
        return
    body = f"{after.author.mention} in <#{after.channel_id}> · [jump]({after.jump_url})"
    body += f"\n**Before:** {before.content[:900]}\n**After:** {after.content[:900]}"
    await log(after.guild, "Message edited", body, 0xFEE75C)


@client.event
async def on_message_delete(message: shoal.Message) -> None:
    # Fires for cached messages, whose content is known; `on_raw_message_delete` fires for every one.
    if not message.author.bot:
        body = f"{message.author.mention} in <#{message.channel_id}>\n{message.content[:1800]}"
        await log(message.guild, "Message deleted", body, 0xED4245)


@client.event
async def on_member_join(member: shoal.Member) -> None:
    created = int(member.created_at.timestamp())
    await log(member.guild, "Member joined", f"{member.mention}, account created <t:{created}:R>", 0x57F287)


@client.event
async def on_member_remove(member: shoal.Member) -> None:
    await log(member.guild, "Member left", f"{member.mention} ({member.name})", 0x99AAB5)


@client.event
async def on_member_update(before: shoal.Member, after: shoal.Member) -> None:
    if before.nick != after.nick:
        names = f"{before.nick or before.name} → {after.nick or after.name}"
        await log(after.guild, "Nickname changed", f"{after.mention}: {names}", 0x5865F2)
    added = set(after.raw_roles) - set(before.raw_roles)
    removed = set(before.raw_roles) - set(after.raw_roles)
    if added or removed:
        changes = [f"+ <@&{role}>" for role in added] + [f"- <@&{role}>" for role in removed]
        await log(after.guild, "Roles changed", f"{after.mention}\n" + "\n".join(changes), 0x5865F2)


client.run(os.environ["DISCORD_TOKEN"])
