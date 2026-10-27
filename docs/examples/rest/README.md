# REST scripts

Shoal's REST client works on its own, with no bot running: from a cron job, a CI pipeline, a web
dashboard or a worker. This script posts an announcement, then sends and edits a message through a
webhook.

```bash
pip install -e "../../.."   # Shoal from this clone (not on PyPI yet)
export DISCORD_TOKEN=your-bot-token
export CHANNEL_ID=channel-to-post-in
python script.py
```

- `RestClient(Token.bot(token))` covers every endpoint Discord documents as
  `rest.<resource>.<verb>`: `rest.messages.create`, `rest.webhooks.execute`, `rest.members.get`, ...
  Each takes a typed params struct, so a misspelt field is a type error, not a 400.
- Rate limits are handled for you: requests wait for their bucket, and 429s are retried.
- `AllowedMentions.none()` keeps `@everyone` in the text from pinging anyone.
- A webhook posts under any name and avatar. `execute(..., wait=True)` returns the message, so it
  can be edited later, here to turn "Deploying" into "Deployed".
- For a dashboard acting as a user, `Token.bearer(...)` takes an OAuth2 access token instead.
