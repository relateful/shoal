# Voice

Shoal joins voice channels, plays audio and listens, with the end-to-end encryption Discord
requires. Install the extra:

```bash
pip install "shoal[voice]"
```

It brings `davey`, a binding of Discord's DAVE protocol library, and `cryptography`. Sending needs no
audio library: Shoal sends Opus as encoded, from an Ogg file or from `ffmpeg`. Only decoding received
audio to PCM needs libopus ([decoded audio](#decoded-audio)).

## Joining and playing

```python
from shoal.models import Member, VoiceChannel
from shoal.voice import FFmpegSource

SONGS = {"intro": "music/intro.mp3", "outro": "music/outro.mp3"}


@bot.command()
async def play(ctx, name: str):
    voice = ctx.voice_client
    if voice is None:
        state = ctx.author.voice if isinstance(ctx.author, Member) else None
        channel = ctx.guild.get_channel(state.channel_id) if state and state.channel_id else None
        if not isinstance(channel, VoiceChannel):
            await ctx.send("Join a voice channel first.")
            return
        voice = await channel.connect()
    voice.play(FFmpegSource(SONGS[name]))
    await voice.wait_until_done()
    await voice.disconnect()
```

`await channel.connect()` sends the voice state update on the guild's shard, waits for Discord's two
answers (the bot's voice session and the voice server to use), then connects. It returns the guild's
`VoiceClient`, which `ctx.voice_client`, `guild.voice_client` and `client.voice_clients` find again.
Pass `self_mute=True` or `self_deaf=True` to join muted or deafened, and `move_to(channel)` to move.

- `OggOpusSource(data)` or `await OggOpusSource.from_path("clip.ogg")` plays Ogg Opus, what Discord's
  own clients record.
- `FFmpegSource(source)` plays anything `ffmpeg` reads (a file, a URL), encoding as it plays, so a long
  file starts at once. `before_options=["-ss", "30"]` starts 30 seconds in, `options=["-af",
  "volume=0.5"]` filters, `bitrate=` sets the Opus bitrate. `ffmpeg` must be installed; it runs
  without a shell, and when it fails the playback ends with an `AudioSourceError` saying why.
- `play(source, after=callback)` calls `after` with the error that stopped playback, or `None`;
  without `after`, the error is logged. `pause()`, `resume()`, `stop()`, `is_playing()` and
  `is_paused()` control it, and `await wait_until_done()` waits for the end; playing while something
  plays raises `AudioPlayingError`.

!!! warning "Never hand `ffmpeg` a user's input unchecked"
    `ffmpeg` opens whatever it is given: local files, internal addresses, playlists that point at
    either. Let users pick from what you allow (as above), or restrict the protocols:
    `FFmpegSource(url, before_options=["-protocol_whitelist", "https,tls,tcp"])`.

Each packet goes out on time, paced against the clock rather than sent as fast as it is read; after
the event loop stalls, playback picks up the schedule rather than send a burst. Five frames of
silence follow a pause or the end, as Discord asks.

## Listening

```python
from shoal.core.ogg import OggOpusWriter
from shoal.voice import opus_samples

writer, recording = OggOpusWriter(), bytearray()
recording += writer.headers()
async for packet in voice.listen():
    if packet.user_id == speaker_id:
        recording += writer.packet(packet.opus, opus_samples(packet.opus))
```

`listen()` yields the Opus packets others send, decrypted, each with who sent it, until the bot
leaves; it follows rejoins and moves. Packets that arrive before Discord names their sender are held
(up to about a second per stream) and come through once it does. Several listeners each get every
packet; packets are only kept while something iterates, and a listener that falls far behind loses
the oldest. `OggOpusWriter` saves them as an `.ogg` file without decoding.

### Decoded audio

```python
import wave

with wave.open("speaker.wav", "wb") as recording:
    recording.setnchannels(2)
    recording.setsampwidth(2)
    recording.setframerate(48000)
    async for frame in voice.audio(user=speaker_id):
        recording.writeframes(frame.pcm)
```

`audio()` decodes what others say to PCM: 48 kHz, stereo, signed 16-bit. Each sender's packets are
put back in order (a late one waits up to three packets behind it), and a lost one is concealed:
rebuilt from the next packet's error correction data when the sender included it, otherwise filled
in by the decoder (`frame.concealed`). A gap of more than five packets is a pause and stays silent;
pauses are not written out as silence, so use `frame.timestamp` to place speech in time.

Decoding needs libopus, a system library: `apt install libopus0` or `brew install opus`. On
Windows, put `opus.dll` in a folder on `PATH`, or name it with
`shoal.voice.receive.load_opus(r"C:\path\to\opus.dll")`: Windows does not look in the bot's own
folder. Shoal finds it on first use. Without it, `audio()` raises `OpusError`;
`listen()` never needs it.

## End-to-end encryption

Since March 1, 2026, Discord carries voice-channel audio only in end-to-end encrypted calls. The
members of a call form an MLS group, and each sender's frames are encrypted with keys only the
members hold; Discord's voice servers relay them without being able to read them. Shoal follows the
protocol on the voice gateway: it sends its key package, commits proposals, applies commits and
welcomes, acknowledges transitions, and asks to be re-added when a commit cannot be applied.
`voice.privacy_code` is the call's voice privacy code, which members can compare to check the
encryption.

Underneath, transport encryption still protects every packet between the bot and the voice server:
AES-256-GCM where the server offers it, XChaCha20-Poly1305 otherwise.

## Staying connected

- A dropped voice websocket, or a voice server that crashed, is resumed: the voice gateway re-sends
  what was missed. Resumes back off when the session keeps dropping, and give up after five tries in
  a row.
- When the session is lost, the voice client joins its channel again by itself (five tries, then it
  leaves).
- Every new voice server answer from Discord (a move, or Discord moving the call to another server)
  is a new session, and the voice client connects again with it.
- When Discord ends the call (the bot was disconnected or kicked), the voice client leaves. When the
  call was terminated (close 4022), it waits for the main gateway to say whether the channel is gone
  or the call moved.

`voice.latency` is the voice heartbeat's round trip. `shoal_voice_reconnects_total` counts resumes
and rejoins, `shoal_voice_packets_dropped_total` the received packets dropped, and
`shoal_voice_frames_concealed_total` the lost ones concealed
([metrics](metrics.md)).

## In clusters

The voice state update goes out on the guild's shard, through the command router when another
cluster runs it ([scaling](scaling.md#clusters)). Discord's answers arrive as events on that cluster,
so join voice from the cluster running the guild's shard, or from a worker receiving its events.

## Without a client

`shoal.voice.VoiceConnection` is the session underneath, usable with the voice server details
(`VoiceServer`: guild, channel, session ID, token and endpoint) and the bot's user ID:

```python
connection = VoiceConnection(server, user_id=bot_id)
await connection.connect()
player = AudioPlayer(lambda: connection, OggOpusSource(data))
await asyncio.wait({player.done})
await connection.close()
```
