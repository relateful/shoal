# Music

A small music bot: `/play` joins your voice channel and plays a song from the `music/` folder or an
HTTPS link, with a queue, `/skip`, `/pause`, `/queue` and `/leave`.

```bash
pip install -e "../../../..[voice]"   # Shoal from this clone (not on PyPI yet)
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: commands appear there at once
python bot.py
```

It needs [ffmpeg](https://ffmpeg.org/download.html) on the `PATH`. Two short chimes are included in
`music/`; drop your own files there and they show up in `/play`'s autocomplete.

- `channel.connect(self_deaf=True)` joins and returns the guild's `VoiceClient`. Discord requires
  end-to-end encryption (DAVE) for voice; `shoal[voice]` brings it, nothing to set up.
- `FFmpegSource` encodes anything ffmpeg reads to Opus as it plays, so long files start at once.
- **One task per server** plays the queue: `voice.play(...)`, then `await voice.wait_until_done()`.
  `/skip` is just `voice.stop()`: the task moves on to the next song.
- **Untrusted input.** ffmpeg opens whatever it is given, local files and internal addresses
  included. `/play` only accepts names of files in `music/` or `https://` links, and limits ffmpeg
  to HTTPS with `-protocol_whitelist https,tls,tcp`.
- Playback is paced against the clock and survives reconnects: if Discord moves the call to another
  voice server, the bot follows and keeps playing.

Recording what others say: [voice/recorder](../recorder/).
