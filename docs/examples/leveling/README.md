# Leveling

Members earn experience for chatting, at most once a minute, and level up as it grows. Data lives
in a SQLite file, so nothing extra to install.

```bash
pip install --pre shoal                       # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: slash commands appear there at once
python bot.py
```

| Try | Shows |
| --- | --- |
| chat | 15 to 25 XP per message, once every 60 seconds per member; a message on level up |
| `/rank`, `!rank @someone` | a hybrid command reading one row |
| `/leaderboard` | the top ten, in an embed that names members without pinging them |

- Overriding `on_message` replaces the bot's own command handling, so it ends with
  `await bot.process_commands(message)`; leave that out and no prefix command runs.
- Levels grow quadratically (`level = isqrt(xp / 100)`): 100 XP for level 1, 400 for level 2, ...
- Discord IDs arrive as `Snowflake`, an `int` subclass; `int(...)` turns them into plain ints for
  SQLite.
- SQLite calls are quick here and run on the event loop. For heavier queries use a database with an
  async driver, or `asyncio.to_thread`.
