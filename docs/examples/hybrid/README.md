# Hybrid commands

Write a command once and use it both ways: `?flip` and `/flip`. Arguments, checks and cooldowns
apply to both; `ctx.send` answers the interaction for a slash use and sends a message for a prefix
use.

```bash
pip install -e "../../.."   # Shoal from this clone (not on PyPI yet)
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: slash commands appear there at once
python bot.py
```

| Try | Shows |
| --- | --- |
| `?flip`, `/flip` | the simplest hybrid command |
| `?choose a, b, c`, `/choose` | a keyword-only parameter: the rest of the message, or one slash option |
| `/profile show`, `?profile show` | a hybrid group; a bare `?profile` shows its help |
| `/profile bio text:` | `Range[str, 1, 100]` limits the option's length on both sides |
| `/slow`, `?slow` | `ctx.defer()`: "thinking…" or "typing…" while it works |

The prefix is `?` or a mention of the bot (`commands.when_mentioned_or`).
