# Reaction roles

Members react to a message to get a role and remove the reaction to lose it.

```bash
pip install -e "../../../.."   # Shoal from this clone (not on PyPI yet)
export DISCORD_TOKEN=your-bot-token
python bot.py
```

In a channel, someone with **Manage Roles** types `!reactionroles`. The bot creates any missing roles
(Red, Green, Blue), posts the menu and adds its reactions. Change `ROLES` in `bot.py` to hand out
your own roles.

- `on_raw_reaction_add` and `on_raw_reaction_remove` fire for every reaction, even on messages sent
  before the bot started, so menus keep working after a restart. Their IDs are saved in
  `reaction_roles.json`.
- The bot's role must sit **above** the roles it hands out (Server Settings → Roles), and it needs the
  Manage Roles permission.
- `bot_has_permissions` refuses the command up front when the bot lacks a permission, instead of
  failing halfway.

For a menu with buttons or a select instead of reactions, see [roles/buttons](../buttons/).
