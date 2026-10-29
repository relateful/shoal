# Reminders

`/remind when: 1h30m what: stretch`, delivered in the same channel when it is due, even if the bot
restarted in between.

```bash
pip install --pre shoal                       # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: commands appear there at once
python bot.py
```

| Command | Shows |
| --- | --- |
| `/remind when what` | parsing `10m`, `1h30m`, `2d`; answering with a relative timestamp `<t:...:R>` |
| `/reminders` | your reminders, soonest first |
| `/forget reminder` | autocomplete that lists your own reminders by text |

- **One background task** sleeps until the next reminder is due. Adding a reminder sets an
  `asyncio.Event`, so a new reminder due sooner wakes it early instead of waiting.
- The task starts in `setup_hook` and waits with `wait_until_ready()` before sending anything.
- Reminders are saved to `reminders.json` (with msgspec, which Shoal already uses) and picked up
  again at start; any that came due while the bot was down are sent at once.
- A reminder whose channel is gone is logged and dropped instead of stopping the task.
