"""A voice recorder: record each speaker to their own Ogg file, then post the files."""

import asyncio
import os
import time
from pathlib import Path
from typing import BinaryIO

import shoal
from shoal import app_commands
from shoal.client import Client
from shoal.core.ogg import OggOpusWriter
from shoal.models import VoiceChannel, VoiceClient
from shoal.voice import opus_samples

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
RECORDINGS = Path("recordings")
UPLOAD_LIMIT = 8 * 1024 * 1024
"""Files larger than this stay on disk instead of being posted."""


class Recording:
    """One recording: an Ogg Opus file per speaker, written as their audio arrives."""

    def __init__(self, voice: VoiceClient) -> None:
        self.voice = voice
        self.folder = RECORDINGS / time.strftime("%Y-%m-%d_%H-%M-%S")
        self.folder.mkdir(parents=True, exist_ok=True)
        self.files: dict[int, tuple[BinaryIO, OggOpusWriter]] = {}
        self.task = asyncio.create_task(self.record())

    async def record(self) -> None:
        async for packet in self.voice.listen():
            if packet.user_id not in self.files:
                writer = OggOpusWriter(serial=len(self.files) + 1)
                file = (self.folder / f"{packet.user_id}.ogg").open("wb")
                file.write(writer.headers())
                self.files[packet.user_id] = (file, writer)
            file, writer = self.files[packet.user_id]
            file.write(writer.packet(packet.opus, opus_samples(packet.opus)))

    async def finish(self) -> list[Path]:
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        for file, writer in self.files.values():
            file.write(writer.packet(b"\xf8\xff\xfe", 960, last=True))  # silence, marking the end
            file.close()
        return sorted(self.folder.glob("*.ogg"))


class Bot(Client):
    def __init__(self) -> None:
        super().__init__(intents=shoal.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.recordings: dict[int, Recording] = {}

    async def setup_hook(self) -> None:
        if GUILD_ID:
            self.tree.copy_global_to(guild=int(GUILD_ID))
            await self.tree.sync(guild=int(GUILD_ID))
        else:
            await self.tree.sync()


bot = Bot()


@bot.tree.command(description="Start recording a voice channel")
@app_commands.default_permissions(manage_guild=True)
@app_commands.guild_only()
async def record(interaction: shoal.Interaction, channel: VoiceChannel) -> None:
    if interaction.guild_id in bot.recordings:
        await interaction.response.send_message("Already recording here.", ephemeral=True)
        return
    await interaction.response.defer()
    voice = await channel.connect()
    bot.recordings[channel.guild_id] = Recording(voice)
    # Tell everyone: recording people without telling them breaks Discord's rules, and trust.
    await interaction.followup.send(f"🔴 Recording {channel.mention}. Use /stop to finish.")


@bot.tree.command(description="Stop recording and post the files")
@app_commands.guild_only()
async def stop(interaction: shoal.Interaction) -> None:
    recording = bot.recordings.pop(interaction.guild_id or 0, None)
    if recording is None:
        await interaction.response.send_message("Not recording.", ephemeral=True)
        return
    await interaction.response.defer()
    paths = await recording.finish()
    await recording.voice.disconnect()
    small = [path for path in paths if path.stat().st_size <= UPLOAD_LIMIT][:10]
    files = [shoal.File(path.name, path.read_bytes()) for path in small]
    summary = f"⏹ Saved {len(paths)} speaker(s) to `{recording.folder}`."
    await interaction.followup.send(summary, files=files)


bot.run(os.environ["DISCORD_TOKEN"])
