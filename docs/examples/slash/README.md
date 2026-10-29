# Slash commands

Slash commands on a plain `Client` with a `CommandTree`: typed options, ranges, choices,
autocomplete, a command group and a right-click (context menu) command.

```bash
pip install --pre shoal                       # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: commands appear there at once
python bot.py
```

| Command | Shows |
| --- | --- |
| `/roll dice sides` | integer options limited with `Range[int, 1, 10]`, defaults |
| `/colour` | fixed `choices` |
| `/fruit` | `autocomplete` that filters as you type |
| `/notes add`, `/notes list` | an `app_commands.Group` with state of its own |
| right-click a user → Apps → Account age | a user context menu |

- Parameters become options; their annotations (`int`, `str`, `shoal.Member`, `Range[...]`) set the
  type Discord shows.
- `setup_hook` runs once after logging in and before connecting: the place to `sync` the tree.
  Global commands can take a while to appear everywhere, so sync to one server while developing.
- Each interaction is answered once, within 3 seconds; `ephemeral=True` shows the answer only to the
  user who asked.
