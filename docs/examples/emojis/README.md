# Application emojis

Custom emojis that belong to the bot itself, so they work in every server without Nitro or a
"emoji server". Put images in `emojis/`, and the bot uploads them and uses them by name.

```bash
pip install -e "../../.."   # Shoal from this clone (not on PyPI yet)
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: commands appear there at once
python bot.py
```

Try `/status` and `/wave`.

- **Declare** each emoji on an `AppEmojis` subclass with a unicode fallback:
  `shoal_online = app_emoji("🟢")`. Until the image is uploaded the fallback is used, so a message
  never shows a blank.
- **Sync** a folder: each file's name is its emoji's name. `icons.sync(folder)` in `setup_hook`
  uploads new and changed images and skips the rest; `emojis/emojis.lock.json` remembers what was
  uploaded. From a shell: `DISCORD_TOKEN=... python -m shoal.emojis sync emojis --dry-run`.
- **Use** them anywhere an emoji goes: in text (`f"{icons.shoal_online} Website"`), reactions,
  buttons and selects.
- An application holds up to 2,000 emojis; each image is at most 256 KiB.
