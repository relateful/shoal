"""Starboard: messages that get enough ⭐ reactions are reposted to #starboard."""

import asyncio
import os
from collections import defaultdict
from pathlib import Path

import msgspec

import shoal
from shoal.client import Client
from shoal.payloads.gateway_events import MessageReactionAdd, MessageReactionRemove

STAR = "⭐"
THRESHOLD = int(os.environ.get("STAR_THRESHOLD", "3"))
STARBOARD = "starboard"
SAVED = Path("starboard.json")
"""Which starboard post belongs to which message, kept across restarts."""

client = Client(intents=shoal.Intents.default())
locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
"""One update at a time per message: two stars at once must not post twice."""
posts: dict[int, int] = msgspec.json.decode(SAVED.read_bytes(), type=dict[int, int]) if SAVED.exists() else {}


def save_posts() -> None:
    SAVED.write_bytes(msgspec.json.encode(posts))


def star_count(message: shoal.Message) -> int:
    return next((reaction.count for reaction in message.reactions if str(reaction.emoji) == STAR), 0)


def starboard_embed(message: shoal.Message) -> shoal.Embed:
    embed = shoal.Embed(description=message.content or None, colour=0xF1C40F, timestamp=message.created_at)
    embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
    embed.add_field(name="Source", value=f"[Jump to message]({message.jump_url})")
    image = next(
        (file for file in message.attachments if (file.content_type or "").startswith("image/")), None
    )
    if image is not None:
        embed.set_image(url=image.url)
    return embed


async def update(event: MessageReactionAdd | MessageReactionRemove) -> None:
    if event.emoji.name != STAR or not isinstance(event.guild_id, int):
        return
    guild = client.get_guild(event.guild_id)
    board = next((c for c in guild.text_channels if c.name == STARBOARD), None) if guild is not None else None
    if board is None or event.channel_id == board.id:
        return
    async with locks[event.message_id]:
        await refresh(board, event.channel_id, event.message_id)


async def refresh(board: shoal.TextChannel, channel_id: int, message_id: int) -> None:
    """Post, update or remove the starboard entry of a message, from its current star count."""
    message = await client.get_partial_messageable(channel_id).fetch_message(message_id)
    stars, posted = star_count(message), posts.get(message.id)
    header = f"{STAR} **{stars}** <#{channel_id}>"
    if posted is None and stars >= THRESHOLD:
        post = await board.send(header, embed=starboard_embed(message))
        posts[int(message.id)] = int(post.id)
    elif posted is not None and stars >= THRESHOLD:
        await board.get_partial_message(posted).edit(content=header)
    elif posted is not None:
        await board.get_partial_message(posted).delete()
        del posts[message.id]
    save_posts()


@client.event
async def on_raw_reaction_add(event: MessageReactionAdd) -> None:
    await update(event)


@client.event
async def on_raw_reaction_remove(event: MessageReactionRemove) -> None:
    await update(event)


client.run(os.environ["DISCORD_TOKEN"])
