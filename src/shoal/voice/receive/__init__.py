"""Receiving audio: received packets decoded to PCM, in order, with losses concealed.

    async for frame in voice.audio():
        recordings[frame.user_id].writeframes(frame.pcm)

Decoding needs libopus, a system library (see `shoal.voice.receive.opus`); packets alone
(`VoiceClient.listen`) do not.

Discord does not document receiving; the transport is the same as sending.

Discord: https://docs.discord.com/developers/topics/voice-connections
"""

from shoal.voice.receive.opus import (
    CHANNELS,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    OpusDecoder,
    OpusError,
    OpusLibrary,
    is_loaded,
    load_opus,
)
from shoal.voice.receive.stream import AudioFrame, Reorderer, decode_audio

__all__ = [
    "CHANNELS",
    "SAMPLE_RATE",
    "SAMPLE_WIDTH",
    "AudioFrame",
    "OpusDecoder",
    "OpusError",
    "OpusLibrary",
    "Reorderer",
    "decode_audio",
    "is_loaded",
    "load_opus",
]
