# Prefix commands

Classic `!commands` with `commands.Bot`: argument conversion, flags, a command group, permission
checks, a cooldown and friendly error messages.

```bash
pip install --pre shoal   # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
python bot.py
```

Enable the **Message Content** and **Server Members** intents in the Developer Portal.

| Try | Shows |
| --- | --- |
| `!add 1 2 3.5` | `*numbers: float`: every remaining word, converted |
| `!userinfo`, `!whois @someone` | `Member \| User` conversion, `commands.Author` as the default, an embed |
| `!echo hi @everyone` | `clean_content()`: mentions written out so they ping nobody |
| `!quickpoll question: Lunch? option: pizza option: sushi` | a `FlagConverter` with a repeatable flag |
| `!tag add name text`, `!tag show name` | a command group |
| `!clean 5` | `has_permissions`, `guild_only`, a per-channel `cooldown`, `Range` |
| `!help`, `!help tag` | the built-in help, from your docstrings |

`on_command_error` turns the common errors (bad input, missing permissions, cooldowns) into replies
and re-raises the rest, so real bugs still reach your logs.
