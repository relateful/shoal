# Button roles

A role menu with buttons (toggle a ping role) and a select menu (pick pronouns), that keeps working
after the bot restarts.

```bash
pip install --pre shoal                       # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: /rolemenu appears there at once
python bot.py
```

Someone with **Manage Roles** runs `/rolemenu`: the bot creates any missing roles and posts the menu.

- **Persistent views.** The view has `timeout=None` and every item a fixed `custom_id`, and
  `setup_hook` registers it with `client.add_view(RoleMenu())`. Clicks on menus posted before a
  restart still reach it.
- **A `ui.Button` subclass** carries its own `callback`, so the buttons are built from `ROLES` in a
  loop; the select is declared with `@ui.select`.
- `@app_commands.default_permissions(manage_roles=True)` hides `/rolemenu` from members who cannot
  manage roles (server admins can change that in Server Settings → Integrations).
- The bot's role must sit above the roles it hands out.

Reactions instead of buttons: [roles/reactions](../reactions/).
