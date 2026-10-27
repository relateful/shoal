"""A music bot: join a voice channel, queue songs, skip, pause and leave."""

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import shoal
from shoal import app_commands
from shoal.app_commands import Choice
from shoal.client import Client
from shoal.models import VoiceChannel, VoiceClient
from shoal.voice import FFmpegSource

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
MUSIC = Path(__file__).with_name("music")
"""Audio files anyone may play by name. URLs are allowed too, over HTTPS only."""


@dataclass
class Player:
    """One server's queue and the task that plays it."""

    voice: VoiceClient
    upcoming: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    """Titles and sources waiting their turn."""
    added: asyncio.Event = field(default_factory=asyncio.Event)
    current: str | None = None
    task: asyncio.Task[None] | None = None

    def add(self, track: tuple[str, str]) -> None:
        self.upcoming.append(track)
        self.added.set()

    async def run(self) -> None:
        while self.voice.is_connected():
            if not self.upcoming:
                self.added.clear()
                await self.added.wait()
                continue
            title, source = self.upcoming.pop(0)
            self.current = title
            options = ["-protocol_whitelist", "https,tls,tcp"] if source.startswith("https://") else []
            self.voice.play(FFmpegSource(source, before_options=options))
            await self.voice.wait_until_done()
            self.current = None


class Bot(Client):
    def __init__(self) -> None:
        super().__init__(intents=shoal.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.players: dict[int, Player] = {}

    async def setup_hook(self) -> None:
        if GUILD_ID:
            self.tree.copy_global_to(guild=int(GUILD_ID))
            await self.tree.sync(guild=int(GUILD_ID))
        else:
            await self.tree.sync()


bot = Bot()


def resolve(song: str) -> tuple[str, str] | None:
    """A song's title and what ffmpeg reads: a file from music/, or an HTTPS URL."""
    if urlparse(song).scheme == "https":
        return song, song
    path = (MUSIC / song).resolve()
    if path.parent == MUSIC.resolve() and path.is_file():
        return path.stem, str(path)
    return None


async def player_for(interaction: shoal.Interaction, channel: VoiceChannel | None) -> Player | None:
    """The server's player, joining `channel` (or the member's channel) when not connected yet."""
    guild = interaction.guild
    if guild is None:
        return None
    player = bot.players.get(guild.id)
    if player is not None and player.voice.is_connected():
        return player
    if channel is None and isinstance(interaction.user, shoal.Member) and interaction.user.voice is not None:
        found = guild.get_channel(interaction.user.voice.channel_id or 0)
        channel = found if isinstance(found, VoiceChannel) else None
    if channel is None:
        return None
    player = Player(await channel.connect(self_deaf=True))
    player.task = asyncio.create_task(player.run())
    bot.players[guild.id] = player
    return player


@bot.tree.command(description="Play a song, or add it to the queue")
@app_commands.describe(song="A file name from the music folder, or an https:// link", channel="Where to play")
@app_commands.guild_only()
async def play(interaction: shoal.Interaction, song: str, channel: VoiceChannel | None = None) -> None:
    track = resolve(song)
    if track is None:
        await interaction.response.send_message(
            "I can only play files I know, or https:// links.", ephemeral=True
        )
        return
    await interaction.response.defer()
    player = await player_for(interaction, channel)
    if player is None:
        await interaction.followup.send("Join a voice channel first, or pick one.")
        return
    player.add(track)
    position = len(player.upcoming)
    await interaction.followup.send(
        f"🎵 **{track[0]}**" + (f" (#{position} in the queue)" if position > 1 else "")
    )


@play.autocomplete("song")
async def song_names(interaction: shoal.Interaction, current: str) -> list[Choice[str]]:
    files = sorted(path.name for path in MUSIC.glob("*") if path.is_file()) if MUSIC.is_dir() else []
    return [Choice(name=name, value=name) for name in files if current.lower() in name.lower()][:25]


@bot.tree.command(description="Show what is playing and what is next")
@app_commands.guild_only()
async def queue(interaction: shoal.Interaction) -> None:
    player = bot.players.get(interaction.guild_id or 0)
    if player is None or player.current is None:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        return
    lines = [f"▶ **{player.current}**"]
    lines += [f"{index}. {title}" for index, (title, _) in enumerate(player.upcoming, start=1)]
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(description="Skip the current song")
@app_commands.guild_only()
async def skip(interaction: shoal.Interaction) -> None:
    player = bot.players.get(interaction.guild_id or 0)
    if player is None or not player.voice.is_playing():
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        return
    player.voice.stop()  # the queue moves on to the next song
    await interaction.response.send_message("⏭ Skipped.")


@bot.tree.command(description="Pause or resume")
@app_commands.guild_only()
async def pause(interaction: shoal.Interaction) -> None:
    player = bot.players.get(interaction.guild_id or 0)
    if player is None:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)
    elif player.voice.is_paused():
        player.voice.resume()
        await interaction.response.send_message("▶ Resumed.")
    else:
        player.voice.pause()
        await interaction.response.send_message("⏸ Paused.")


@bot.tree.command(description="Stop and leave the voice channel")
@app_commands.guild_only()
async def leave(interaction: shoal.Interaction) -> None:
    player = bot.players.pop(interaction.guild_id or 0, None)
    if player is None:
        await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)
        return
    if player.task is not None:
        player.task.cancel()
    await player.voice.disconnect()
    await interaction.response.send_message("👋 Bye.")


bot.run(os.environ["DISCORD_TOKEN"])
