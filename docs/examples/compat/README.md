# Moving from discord.py

A discord.py bot running on Shoal through `shoal.compat`: the imports change, and the few lines
marked `CHANGED` in `bot.py`. Everything else is the code you already have.

```bash
pip install --pre shoal   # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
python bot.py
```

Then `!sync` (as the bot's owner) registers the slash commands in that server, and `!hello`,
`/created` and right-click → Apps → Avatar work as before.

```python
import shoal.compat as discord
from shoal.compat import app_commands, commands
```

`discord.Member` is `shoal.Member`, `discord.Forbidden` is `shoal`'s `ForbiddenError`,
`discord.utils.format_dt` and `discord.utils.get` are there: the same objects under the names you
know, so a bot can move file by file.

What does change:

- **Flags are immutable.** `intents.message_content = True` becomes
  `Intents.default().with_flags(message_content=True)`; the same for `Permissions`.
- **Exception names end in `Error`** in Shoal's own names (`commands.CommandOnCooldownError`,
  `ForbiddenError`). `shoal.compat` keeps the old names as well (`commands.CommandOnCooldown`,
  `discord.Forbidden`, `discord.HTTPException`), so existing `except` clauses keep working.
- **Absent and `null` differ** in payloads (`UNSET` and `None`), where discord.py turns both into
  `None`.
- Syncing to one server needs `tree.copy_global_to(guild=...)` first, as in discord.py; without it
  the server gets an empty set.

The [migration guide](../../guide/migrating-from-discord-py.md) maps every name; new code reads
better with Shoal's own names.
