# Polls

Two kinds of vote: Discord's own polls, and a button vote whose tally the bot updates live.

```bash
pip install --pre shoal                       # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: commands appear there at once
python bot.py
```

| Command | Shows |
| --- | --- |
| `/poll question answers: a, b, c hours multiple` | a native poll (`PollCreateRequest`), up to 10 answers |
| `/vote question` | buttons that edit their own message with `response.edit_message` |

- Native polls are counted by Discord and shown in every client; `on_raw_poll_vote_add` and
  `on_raw_poll_vote_remove` tell the bot about each vote. A poll cannot be edited once sent;
  `rest.polls.end(channel_id, message_id)` closes it early.
- The button vote keeps its tally in the view: one vote per member, changeable, and the message
  shows the new count with every click. It stops answering after an hour (`timeout=3600`).
