# Giveaways

`/giveaway prize minutes winners` posts a giveaway with an Enter button; when the time is up, the
bot draws the winners and announces them. Running giveaways survive a restart.

```bash
pip install --pre shoal                       # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: /giveaway appears there at once
python bot.py
```

Someone with **Manage Server** runs `/giveaway`.

- **Enter and leave.** Pressing the button again leaves the giveaway; each press answers privately.
- **Persistent.** The button has a fixed `custom_id` and the view no timeout, registered with
  `add_view` in `setup_hook`, so it answers on giveaways posted before a restart. Entrants and end
  times are saved to `giveaways.json` with msgspec, and `setup_hook` schedules the draws again.
- **On time.** One task per giveaway sleeps until its end; the bot keeps a reference to each task
  (the event loop only holds tasks weakly, so an unreferenced one can be collected mid-sleep).
- **The draw** edits the original message to show the winners and removes its button
  (`edit(view=None)`), then announces them in the channel.
- Discord IDs arrive as `Snowflake`, an `int` subclass; they are saved as plain `int`s, which msgspec
  writes.
