# Roadmap

What is built is described in the guides. This page is what comes next, in rough order, and why.

## 1. The bot API

- **Models with behaviour** over the payloads (`Message.reply`, `Member.add_roles`), backed by the
  cache and the REST client, with discord.py's names where they are good.
- **Commands, slash first.** Discord denies the Message Content intent to verified apps whose only
  reason is prefix commands, so application commands are the default. **Hybrid commands** (one
  definition, slash and prefix) remain for bots that can use both.
- **Cogs, checks, cooldowns, converters** in the shape discord.py users know.
- **Components v2 and modals**, with persistent views that survive restarts like the cache does.
- **A discord.py compatibility layer**: aliases such as `discord.NotFound` and the common
  `ext.commands` surface, so a migration can be incremental.

## 2. An application emoji manager

Built from what running greed taught us:

- a typed name registry (`Emoji.check`), so a missing emoji is a type error, not a blank in a message;
- a unicode fallback for every emoji, so output never renders as nothing before the registry loads;
- uploads that run one at a time behind a shared 429 barrier, so a sync converges in one run;
- recovery for names left taken by an interrupted upload (`APPLICATION_EMOJI_NAME_ALREADY_TAKEN`);
- hashing, so unchanged assets are skipped; pruning off by default.

## 3. Shared state for clusters

- Redis implementations of `IdentifyLimiter`, `SessionStore`, `RateLimiter` and `CacheCollection`,
  so clusters on many hosts share identify slots, sessions, rate limits and cache.
- A **REST proxy** server: one process owns the rate limits, every bot and dashboard talks to it.
- IPC over Unix sockets, and an optional broker transport (NATS or Redis streams).
- Resharding without downtime, using Discord's support for parallel sessions with a new shard count.

## 4. The rest of the Discord API

Every HTTP endpoint and every gateway event Discord documents is implemented; `docs/coverage.md`
shows both and CI fails when Discord documents something new, and the cache follows every event that
changes something it holds. Still to come: the outgoing webhook events Discord sends to an app, and
voice messages.

## 5. Voice

Voice send with DAVE end-to-end encryption, then receive as an optional extension.
