# Cogs and extensions

Split a bot into files. Each file in `cogs/` is an extension: a module with a `setup` function that
adds a `Cog`, a class grouping commands, slash commands and listeners. The bot loads every file at
start, and the owner can reload one while it runs.

```
cogs/
  bot.py        loads every extension in cogs/
  cogs/fun.py   hybrid commands and a message listener
  cogs/admin.py owner-only !load, !unload, !reload, !sync
```

```bash
pip install --pre shoal                       # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: slash commands appear there at once
python bot.py
```

Run it from this folder, so `cogs.fun` can be imported.

- Edit `cogs/fun.py` while the bot runs, then `!reload fun`: the new code takes over. If the new
  version fails to load, the old one stays.
- `!unload fun` removes its commands, its listener and its slash commands; `!sync` tells Discord.
- `@commands.is_owner()` checks the application's owner (or team), fetched the first time.
- `cog_command_error` handles the errors of one cog's commands.
