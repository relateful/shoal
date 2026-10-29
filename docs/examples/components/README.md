# Components V2

Messages built from layout components instead of content and embeds: containers with an accent
colour, sections with a thumbnail, separators, image galleries and buttons placed anywhere.

```bash
pip install --pre shoal                       # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: commands appear there at once
python bot.py
```

| Command | Shows |
| --- | --- |
| `/server` | a `LayoutView` built in code from live data; Refresh redraws it with `edit_message` |
| `/notes` | a layout declared on the class, with a button declared through its row (`@actions.button`) |

- A `LayoutView` **is** the message: it replaces `content` and `embeds`, so sending it with either
  raises `TypeError` before Discord would refuse it.
- `ui.Section(text, accessory=ui.Thumbnail(url))` puts an image (or a button) beside text;
  `ui.MediaGallery` shows up to 10 images; `ui.Separator` adds space or a line.
- Markdown works in `TextDisplay`: headings (`#`, `##`, `###`), lists, and `-#` for small text.
- A message holds at most 40 components, counting those inside others; Shoal checks that before
  sending.
- Buttons made in code get their callback assigned (`refresh.callback = self.refresh`); buttons
  declared on the class use decorators.
