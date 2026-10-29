# Moderation

`/timeout`, `/untimeout`, `/kick`, `/ban` and `/purge`, with the checks a real server needs, reasons
recorded in the audit log, and a `#mod-log` channel.

```bash
pip install --pre shoal                       # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: commands appear there at once
python bot.py
```

Create a `#mod-log` channel to have every action recorded there.

- `@app_commands.default_permissions(kick_members=True)` hides each command from members without
  that permission; server admins can adjust it per role in Server Settings → Integrations.
- `@app_commands.checks.bot_has_permissions(...)` answers "I need: ..." instead of failing halfway
  when the bot lacks a permission; `@bot.tree.error` turns that and cooldowns into replies.
- `can_act` refuses to act on yourself, the server owner, or anyone whose top role is not below the
  moderator's, as Discord's own role hierarchy would.
- `reason=` goes to the audit log; `delete_message_seconds` removes a banned member's recent
  messages.
- `/purge` defers first (deleting can take a moment), then answers with a follow-up.
