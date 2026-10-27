"""Voice messages: send audio that plays inline, with a waveform, like a recorded message."""

import asyncio
import os
from pathlib import Path

import aiohttp

import shoal
from shoal import app_commands
from shoal.client import Client
from shoal.payloads import Attachment
from shoal.rest.files import waveform_of

GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
SAMPLE = Path(__file__).with_name("chime.ogg")


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


@bot.tree.command(description="Send the sample voice message")
async def chime(interaction: shoal.Interaction) -> None:
    # The duration is read from the Ogg Opus file; without a waveform the preview is flat.
    voice = await shoal.VoiceMessage.from_path(SAMPLE)
    await interaction.response.send_message(voice_message=voice)


@bot.tree.command(description="Turn an uploaded audio file into a voice message")
@app_commands.describe(audio="Any audio file ffmpeg can read")
async def convert(interaction: shoal.Interaction, audio: Attachment) -> None:
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session, session.get(audio.url) as response:
        original = await response.read()
    encoded = await ffmpeg(original, "-c:a", "libopus", "-b:a", "48k", "-ar", "48000", "-f", "ogg")
    # Mono 8 kHz, one byte a sample: 800 samples per 100 ms slice, each slice's level its peak.
    samples = await ffmpeg(original, "-ac", "1", "-ar", "8000", "-f", "u8")
    slices = [samples[start : start + 800] for start in range(0, len(samples), 800)]
    levels = [max(abs(sample - 128) for sample in piece) / 128 for piece in slices if piece]
    if not encoded or not levels:
        await interaction.followup.send("ffmpeg could not read that file.")
        return
    voice = shoal.VoiceMessage.from_ogg(encoded, waveform=waveform_of(levels))
    await interaction.followup.send(voice_message=voice)


async def ffmpeg(data: bytes, *output: str) -> bytes:
    """Run ffmpeg on `data` (standard input) and return what it writes to standard output."""
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", *output, "pipe:1",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
    )  # fmt: skip
    result, _ = await process.communicate(data)
    return result


bot.run(os.environ["DISCORD_TOKEN"])
