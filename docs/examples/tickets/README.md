# Tickets

A support desk: members press a button, fill in a short form, and get a private channel that only
they, staff and the bot can see. Staff close it with a button.

```bash
pip install --pre shoal                       # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: /ticketpanel appears there at once
export STAFF_ROLE=Staff                       # optional: the role that sees every ticket
python bot.py
```

Someone with **Manage Channels** runs `/ticketpanel` where the button should live.

- **Modal.** `TicketForm` is a `ui.Modal` with two `TextInput`s; `on_submit` reads them with
  `str(self.topic)`.
- **Private channels.** Permission overwrites hide the channel from `@everyone` (the role whose ID is
  the server's) and open it to the member, the staff role and the bot. Tickets go in a `Tickets`
  category, created on first use.
- **Persistent views.** Both the panel and the close button survive restarts: fixed `custom_id`s, no
  timeout, and `add_view` in `setup_hook`.
- The modal answers with `defer` then a follow-up, because creating the channel can take more than
  the 3 seconds Discord allows for a first answer.

The bot needs **Manage Channels** and **Manage Roles** (to set overwrites).
