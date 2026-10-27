# Server logs

Records what happens in a server in a `#logs` channel: edited and deleted messages, members joining
and leaving, nickname and role changes.

```bash
pip install -e "../../.."   # Shoal from this clone (not on PyPI yet)
export DISCORD_TOKEN=your-bot-token
python bot.py
```

Create a `#logs` channel the bot can write in, and enable the **Message Content** and **Server
Members** intents in the Developer Portal.

- **The cache gives you "before".** `on_message_edit(before, after)`, `on_message_delete(message)`
  and `on_member_update(before, after)` fire for things the bot had cached, so the old content,
  nickname or roles are known. Their raw versions (`on_raw_message_edit`, `on_raw_message_delete`,
  `on_raw_member_update`) fire for everything, with only what Discord sends.
- Messages are cached as they arrive; by default the last 1,000 are kept
  ([caching](../../guide/caching.md) changes that per kind).
- Log embeds use `AllowedMentions(users=[], roles=[])`: they name members and roles without pinging
  anyone.
