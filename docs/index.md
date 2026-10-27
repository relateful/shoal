---
template: home.html
title: Shoal
description: A fully typed Discord API library for Python, built for bots that grow.
hero_title: From one server to a million, without a rewrite.
hero_lead: >-
  Shoal is a fully typed Discord library for Python. Start with one process and one shard; when the
  bot grows, split the gateway, the cache and your code across processes and machines with the same
  objects you started with.
hero_caption: Every fish is a shard. They identify in parallel, resume after a restart, and move as one.
primary_label: Read the guide
primary_link: guide/architecture.md
secondary_label: Browse the API
secondary_link: reference/shoal/index.md
---

<div class="home-status" markdown>

<p class="status-tag">Pre-alpha</p>

<p markdown="span">Built and tested: typed payloads, a REST client that covers every endpoint Discord documents, the gateway, the cache, IPC, state shared through Redis, a REST proxy, resharding without downtime, metrics and diagnostics, and the bot API on top: a `Client` with models, slash, prefix and hybrid commands, cogs, views, modals and layouts, voice messages, end-to-end encrypted voice with decoded receive, loops and a scheduler for jobs that survive restarts, and the application's emojis. Start with [writing a bot](guide/bot.md); the [roadmap](roadmap.md) has what comes next.</p>

</div>

<section class="home-section" markdown>

<div class="section-intro" markdown>

## What changes when you switch from discord.py

The same Python and the same asyncio. The difference shows when the bot gets big, when something
goes wrong, and in the types you write against.

The [migration guide](guide/migrating-from-discord-py.md) maps the names you already know.

</div>

<div class="section-body switch" markdown>

<div class="switch-head" aria-hidden="true"><span></span><span>discord.py</span><span>Shoal</span></div>

<div class="switch-group" markdown>

<h3 class="switch-title">As the bot grows</h3>

<div class="switch-row" markdown>
<p class="switch-when">512 shards start up</p>
<p class="switch-old" markdown="span">One shard every 5 seconds, whatever Discord allows: about 43 minutes.</p>
<p class="switch-new" markdown="span">Every `max_concurrency` bucket at once. With 16 buckets, under 3 minutes.</p>
<div class="switch-race" role="img" aria-label="Start-up time for 512 shards: 42 minutes 40 seconds with discord.py, 2 minutes 40 seconds with Shoal and 16 buckets.">
<span class="race race-old" style="--share: 100%"><span>42 min 40 s</span></span>
<span class="race race-new" style="--share: 6.25%"><span>2 min 40 s</span></span>
</div>
</div>

<div class="switch-row" markdown>
<p class="switch-when">You deploy a new version</p>
<p class="switch-old" markdown="span">Every shard identifies again, every guild is sent again, and the cache starts empty.</p>
<p class="switch-new" markdown="span">Shards resume where they stopped, and the cache comes back from a snapshot.</p>
</div>

<div class="switch-row" markdown>
<p class="switch-when">One process is not enough</p>
<p class="switch-old" markdown="span">No built-in way to split the gateway from your code.</p>
<p class="switch-new" markdown="span">Gateway processes stream events to worker processes over authenticated TCP.</p>
</div>

</div>

<div class="switch-group" markdown>

<h3 class="switch-title">When something goes wrong</h3>

<div class="switch-row" markdown>
<p class="switch-when">Your code blocks the event loop</p>
<p class="switch-old" markdown="span">A stack trace, once the heartbeat has been stuck for 10 seconds.</p>
<p class="switch-new" markdown="span">The blocking line of your code, within a quarter of a second.</p>
</div>

<div class="switch-row" markdown>
<p class="switch-when">Messages arrive 15 s late on a 50 ms ping</p>
<p class="switch-old" markdown="span">Nothing tells you.</p>
<p class="switch-new" markdown="span">The delay is measured on every message, and the likely cause is logged.</p>
</div>

<div class="switch-row" markdown>
<p class="switch-when">The bot token is revoked</p>
<p class="switch-old" markdown="span">Every request keeps failing, and each failure counts towards a Cloudflare IP ban.</p>
<p class="switch-new" markdown="span">Requests stop after the first 401.</p>
</div>

</div>

<div class="switch-group" markdown>

<h3 class="switch-title">While you write code</h3>

<div class="switch-row" markdown>
<p class="switch-when">Discord adds a new enum value</p>
<p class="switch-old" markdown="span">You get an `unknown_` stand-in that is not a member of the enum.</p>
<p class="switch-new" markdown="span">You get a real member of the enum, with its value kept.</p>
</div>

<div class="switch-row" markdown>
<p class="switch-when" markdown="span">A field is missing, or `null`</p>
<p class="switch-old" markdown="span">Both become `None`.</p>
<p class="switch-new" markdown="span">`UNSET` and `None` stay apart, so an update can tell "leave it" from "clear it".</p>
</div>

<div class="switch-row" markdown>
<p class="switch-when">You build a dashboard</p>
<p class="switch-old" markdown="span">You reach for the undocumented `Client.http`.</p>
<p class="switch-new" markdown="span">You use `RestClient`: public, standalone, with OAuth2 bearer tokens.</p>
</div>

</div>

</div>

</section>

<section class="home-section home-code" markdown>

<div class="section-intro" markdown>

## The same library at both ends

A script that sends one message and a bot in thousands of guilds use the same client, the same
payloads and the same errors.

</div>

<div class="section-body split" markdown>

<div markdown>

### A dashboard or a script

The REST client needs no gateway and no cache.

```python
from shoal.payloads import (
    AllowedMentions,
    CreateMessageParams,
)
from shoal.rest import RestClient, Token

async with RestClient(Token.bot(token)) as rest:
    me = await rest.users.get_me()
    await rest.messages.create(
        channel_id,
        CreateMessageParams(
            content=f"hello from {me.username}",
            allowed_mentions=AllowedMentions.none(),
        ),
    )
```

</div>

<div markdown>

### A bot in thousands of guilds

Shards resume across restarts and feed a cache that survives them.

```python
store = CacheStore(metrics=metrics)
await store.load_snapshot("cache.msgpack", shard_count=gateway.shards)

manager = ShardManager(
    token=token,
    intents=intents,
    dispatch=CacheUpdater(store, intents=intents).apply,
    shard_count=gateway.shards,
    identify_limiter=LocalIdentifyLimiter(16),
    session_store=FileSessionStore("sessions/"),
    metrics=metrics,
)
await manager.run()
```

</div>

</div>

</section>

<section class="home-section home-layers" markdown>

<div class="section-intro" markdown>

## Layers you can run apart

Each layer depends only on the layers below it, never on one beside it, so every upper layer can
live in its own process.

The [architecture guide](guide/architecture.md) explains what each layer owns.

</div>

<div class="section-body layers" markdown>

<div class="layer-row layer-top" markdown>

[rest](reference/shoal/rest/index.md){ .layer } [gateway](reference/shoal/gateway/index.md){ .layer } [cache](reference/shoal/cache/index.md){ .layer } [ipc](reference/shoal/ipc/index.md){ .layer } [metrics](reference/shoal/metrics/index.md){ .layer } [diagnostics](reference/shoal/diagnostics/index.md){ .layer } [endpoint](reference/shoal/endpoint/index.md){ .layer } [tasks](reference/shoal/tasks/index.md){ .layer }

</div>

<div class="layer-row" markdown>

[payloads: every Discord object, typed and linked to Discord's docs](reference/shoal/payloads/index.md){ .layer .layer-wide }

</div>

<div class="layer-row" markdown>

[core: snowflakes, flags, enums, the codec, clocks and metrics](reference/shoal/core/index.md){ .layer .layer-wide }

</div>

</div>

</section>
