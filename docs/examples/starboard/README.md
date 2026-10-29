# Starboard

Messages that collect enough ⭐ reactions are reposted to a `#starboard` channel; the count stays up
to date, and the post goes away if the stars do.

```bash
pip install --pre shoal       # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
export STAR_THRESHOLD=3       # optional: stars needed, 3 by default
python bot.py
```

Create a `#starboard` channel the bot can write in.

- Raw reaction events fire for any message, cached or not; the bot fetches the message to read its
  current ⭐ count rather than counting events itself, so missed events never skew it.
- **One update at a time per message.** Two members starring at once send two events; without the
  per-message `asyncio.Lock`, both would see "not posted yet" and post twice.
- The link between a message and its starboard post is saved in `starboard.json`, so edits and
  removals still find the post after a restart. msgspec writes it; Shoal already depends on msgspec.
- Images attached to the message show in the starboard embed.
