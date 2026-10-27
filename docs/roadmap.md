# Roadmap

What is built is described in the guides. Everything the previous roadmap planned is built:

- **The bot API**, including Components V2 layouts and the familiar names of `shoal.compat`
  ([writing a bot](guide/bot.md), [migrating](guide/migrating-from-discord-py.md)).
- **Shared state for clusters**: Redis implementations of the identify limiter, session store, rate
  limiter and cache; a REST proxy; IPC over Unix sockets and through a Redis stream; a shard
  directory and command routing between clusters; resharding without downtime
  ([scaling](guide/scaling.md), [caching](guide/caching.md)).
- **Voice messages** ([writing a bot](guide/bot.md#voice-messages)).
- **Voice** with DAVE end-to-end encryption: joining, playing and listening ([voice](guide/voice.md)).

Nothing new is planned yet. Shoal keeps up with Discord's API as it changes: CI compares every
endpoint and event with Discord's documentation each week, and mirrors each change Discord makes to
it as a pull request.
