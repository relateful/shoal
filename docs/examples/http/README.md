# HTTP interactions

A bot with no gateway connection: Discord sends each slash command and button press to this web
server as an HTTP request, and the answer goes back in the HTTP reply. Nothing stays connected to
Discord. Views (like the counter) live in the process that sent them, so run one process, or route a
message's clicks back to it.

```bash
pip install --pre "shoal[interactions]"         # Shoal from PyPI
export DISCORD_TOKEN=your-bot-token
export DISCORD_PUBLIC_KEY=your-app-public-key   # Developer Portal → General Information
export DISCORD_GUILD_ID=your-test-server-id     # optional: commands appear there at once
python bot.py
```

Discord only calls HTTPS URLs. Put the server behind a reverse proxy or a tunnel
(`cloudflared tunnel --url http://localhost:8080`), then set **Interactions Endpoint URL** in the
Developer Portal to `https://<your host>/interactions`. Discord checks the URL with a signed `PING`
when you save it.

> [!IMPORTANT]
> Once the URL is set, Discord sends interactions there **instead of** over the gateway, for every
> process using this application.

- `bot.login(token)` checks the token and runs `setup_hook`; no `connect`, so no intents are needed.
- `bot.endpoint(public_key)` verifies Discord's Ed25519 signature on every request (anything else
  gets a 401), answers `PING` itself, and routes the rest through the same commands, views and
  modals a gateway bot uses.
- The first response becomes the HTTP reply. `defer()` replies "thinking…" at once, and the
  follow-up goes through Discord's API later, so slow commands are fine.
- What needs the gateway is not available: events, the cache, voice.
