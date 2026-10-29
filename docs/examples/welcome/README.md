# Welcome

Greets new members with an embed, gives them a role, and says goodbye when they leave.

```bash
pip install --pre shoal       # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
export AUTOROLE=Member        # optional: the role new members get
python bot.py
```

Enable the **Server Members** intent in the Developer Portal: without it Discord sends no join or
leave events.

- Messages go to the server's system channel (Server Settings → Overview), or to a `#welcome`
  channel.
- `allowed_mentions=AllowedMentions(users=[member.id])` pings the new member and nobody else, even if
  the message ever contains other mentions.
- `on_raw_member_remove` fires for every leave, even for members the bot never cached; the friendlier
  `on_member_remove` fires only when the member was cached.
- The bot's role must sit above the autorole, with the Manage Roles permission.
