# Voice messages

Send audio that plays inline with a waveform, like a message recorded on a phone.

```bash
pip install -e "../../../.."   # Shoal from this clone (not on PyPI yet)
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: commands appear there at once
python bot.py
```

| Command | Shows |
| --- | --- |
| `/chime` | `VoiceMessage.from_path("chime.ogg")`: the included sample, sent as is |
| `/convert audio:` | any uploaded audio file encoded with ffmpeg, with a real waveform |

`/convert` needs [ffmpeg](https://ffmpeg.org/download.html) on the `PATH`; `/chime` does not.

- A voice message is **Ogg Opus** audio, what Discord's own clients record. Its duration is read
  from the stream, so you never pass it.
- The **waveform** is the loudness of each 100 ms; `waveform_of(levels)` packs it the way Discord
  expects (up to 256 points). Without one the preview is flat.
- A voice message goes alone: no text, embeds, other files or components, and it cannot be edited
  later. Shoal raises `TypeError` before sending anything else with it.
- The bot needs the **Send Voice Messages** permission in the channel.
- ffmpeg reads the upload from standard input and writes to standard output: no temporary files.
