# Roadmap

What is built is described in the guides. This page is what comes next, in rough order, and why.

## 1. Finishing the bot API

The bot API is built: models, slash, prefix and hybrid commands, cogs, extensions, views, modals and
the application's emojis ([writing a bot](guide/bot.md)). Still planned:

- **Components v2** layouts (sections, containers, media galleries) in `ui`.
- **A discord.py compatibility layer**: aliases such as `discord.NotFound` and the rest of the
  `ext.commands` surface (`FlagConverter`, `clean_content`, `commands.param`,
  `app_commands.Transformer`, dynamic cooldowns), so a migration can be incremental.

## 2. Shared state for clusters

- Redis implementations of `IdentifyLimiter`, `SessionStore`, `RateLimiter` and `CacheCollection`,
  so clusters on many hosts share identify slots, sessions, rate limits and cache.
- A **REST proxy** server: one process owns the rate limits, every bot and dashboard talks to it.
- IPC over Unix sockets, and an optional broker transport (NATS or Redis streams).
- Resharding without downtime, using Discord's support for parallel sessions with a new shard count.

## 3. The rest of the Discord API

Every HTTP endpoint and every gateway event Discord documents is implemented; `docs/coverage.md`
shows both and CI fails when Discord documents something new, and the cache follows every event that
changes something it holds, and the webhook events Discord posts to an app are received by
`Endpoint`. Still to come: voice messages.

## 4. Voice

Voice send with DAVE end-to-end encryption, then receive as an optional extension.
