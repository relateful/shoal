# Forms

`/apply` opens a staff application: a modal using the newer inputs Discord allows in modals, not
just text fields.

```bash
pip install -e "../../.."   # Shoal from this clone (not on PyPI yet)
export DISCORD_TOKEN=your-bot-token
export DISCORD_GUILD_ID=your-test-server-id   # optional: /apply appears there at once
python bot.py
```

Create an `#applications` channel to receive submitted applications there.

| Input | Read after submission |
| --- | --- |
| `ui.TextInput` (paragraph) | `str(self.intro)` |
| `ui.RadioGroup` | `self.team.value` |
| `ui.CheckboxGroup` | `self.days.values` |
| `ui.Select` | `self.timezone.values` |
| `ui.FileUpload` | `self.examples.values`: the uploaded attachments |

- Every input sits in a `ui.Label`, which gives it a title and an optional description. A single
  yes/no `ui.Checkbox` works the same way; `ui.TextDisplay` adds text between inputs.
- A modal holds **at most five** items. Shoal refuses a sixth as it is added, rather than letting
  Discord fail the interaction.
- The inputs are made in `__init__` and kept as attributes, so `on_submit` reads them directly.
- `on_submit` runs in its own task: a slow one never holds up other interactions.
