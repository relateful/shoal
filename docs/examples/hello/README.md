# Hello

The smallest bot there is: it answers `ping` with `pong`.

```bash
pip install --pre shoal   # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
python bot.py
```

Then type `ping` in any channel the bot can read.

- `Client(intents=...)` connects every shard Discord recommends; `client.run` stops cleanly on Ctrl+C.
- Reading message text needs the **Message Content** intent, both in code
  (`with_flags(message_content=True)`) and in the Developer Portal (Bot → Privileged Gateway Intents).
- `@client.event` registers a handler by its name: `on_ready`, `on_message`, `on_member_join`, ...
