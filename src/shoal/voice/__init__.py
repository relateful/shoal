"""Voice connections: the voice gateway, UDP, transport encryption, DAVE and audio (`shoal[voice]`).

Every voice channel carries end-to-end encrypted audio (DAVE) since March 1, 2026; Shoal follows the
protocol on the voice gateway and encrypts with `davey`, a binding of Discord's protocol library.
Most bots join through the models (`await channel.connect()`, a `shoal.models.voice.VoiceClient`);
`VoiceConnection` is the session underneath, usable on its own with the voice server details.

Discord: https://docs.discord.com/developers/topics/voice-connections
"""

from shoal.voice import defaults
from shoal.voice.audio import AudioPlayer, AudioSource, FFmpegSource, OggOpusSource
from shoal.voice.connection import VoiceConnection, VoiceConnectionClosedError, VoicePacket, VoiceServer
from shoal.voice.crypto import TransportCipher, hchacha20
from shoal.voice.dave import MAX_PROTOCOL_VERSION, Dave
from shoal.voice.rtp import RtpHeader, opus_samples, parse_rtp, rtp_header
from shoal.voice.udp import UdpTransportFactory, VoiceTransport, VoiceTransportFactory, discover

__all__ = [
    "MAX_PROTOCOL_VERSION",
    "AudioPlayer",
    "AudioSource",
    "Dave",
    "FFmpegSource",
    "OggOpusSource",
    "RtpHeader",
    "TransportCipher",
    "UdpTransportFactory",
    "VoiceConnection",
    "VoiceConnectionClosedError",
    "VoicePacket",
    "VoiceServer",
    "VoiceTransport",
    "VoiceTransportFactory",
    "defaults",
    "discover",
    "hchacha20",
    "opus_samples",
    "parse_rtp",
    "rtp_header",
]
