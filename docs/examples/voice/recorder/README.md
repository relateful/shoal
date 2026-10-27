# Voice recorder

`/record channel` joins a voice channel and saves what each person says to their own `.ogg` file;
`/stop` leaves and posts the files.

```bash
pip install -e "../../../..[voice]"   # Shoal from this clone (not on PyPI yet)
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: commands appear there at once
python bot.py
```

> [!WARNING]
> Tell people they are being recorded. Recording without consent breaks Discord's Developer Policy
> and, in many places, the law. The bot announces every recording in the channel it was started
> from, and only members with **Manage Server** see `/record` by default.

- `voice.listen()` yields every Opus packet others send, already decrypted (transport encryption and
  DAVE end-to-end encryption), each with the `user_id` of who said it. It follows the bot through
  reconnects and moves, and ends when the bot leaves.
- `OggOpusWriter` turns those packets into a standard Ogg Opus file any player opens, with no audio
  library and no re-encoding. `opus_samples` reads each packet's length, so timing is exact.
- Files are written as audio arrives, into `recordings/<date and time>/<user id>.ogg`. Files up to
  8 MiB are posted when the recording stops; larger ones stay on disk.
- Silence is not recorded: Discord sends nothing while someone is quiet, so each file holds the
  speaker's speech back to back.
