# Paginator

Long lists split into embed pages, with first / previous / next / last buttons and a page counter.
Only the member who ran the command can turn the pages, and the buttons grey out after two minutes.

```bash
pip install -e "../../.."   # Shoal from this clone (not on PyPI yet)
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: commands appear there at once
python bot.py
```

Try `/numbers` (100 lines, 10 pages) or `/roles` (this server's roles).

- `Paginator` is a reusable `ui.View`: give it any list of embeds. `pages_of` splits lines into
  pages.
- Buttons made in code get their `callback` assigned; `arrow` builds one per direction, so the
  page each one shows is a small function.
- `interaction_check` runs before any button: returning `False` stops the click, here with a
  private note to whoever tried.
- `on_timeout` disables the buttons and edits the message, which `original_response()` found right
  after sending.
