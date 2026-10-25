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

<section class="home-section home-status" markdown>

Shoal is **pre-alpha**. The foundation is complete and tested: typed payloads, the REST client, the
gateway, the cache, IPC, metrics and diagnostics. Models with methods, commands and components come
next; the [roadmap](roadmap.md) has the order.

</section>

<section class="home-section" markdown>

## What changes when you switch from discord.py

<div class="compare" markdown>

| When | discord.py | Shoal |
| --- | --- | --- |
| 512 shards start | One every 5 seconds, about 43 minutes | By `max_concurrency` bucket, about 3 minutes with 16 |
| You deploy | Every guild is sent again, the cache starts empty | Sessions resume, the cache comes back from a snapshot |
| The bot outgrows one process | Bring your own IPC | Gateway processes stream events to worker processes |
| Your code blocks the loop | A stack trace after 10 seconds of missed heartbeats | The blocking line, within a quarter second |
| Events arrive late | Nothing tells you | The delay is measured and the cause suggested |
| A token is revoked | Requests keep failing and count towards an IP ban | Requests stop after the first 401 |
| Discord adds an enum value | An `unknown_` stand-in object | A real member of the enum |
| You want a dashboard | The undocumented `Client.http` | A public `RestClient` with OAuth2 bearer tokens |

</div>

The [migration guide](guide/migrating-from-discord-py.md) maps the names you already know.

</section>

<section class="home-section home-code" markdown>

## The same library at both ends

<div class="split" markdown>

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
    me = await rest.get_current_user()
    await rest.create_message(
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
await store.load_snapshot("cache.msgpack")

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

## Layers you can run apart

Everything depends on the two layers below it and nothing beside it, so each upper layer can live in
its own process.

<div class="layers" markdown>

<div class="layer-row layer-top" markdown>

[rest](reference/shoal/rest/index.md){ .layer } [gateway](reference/shoal/gateway/index.md){ .layer } [cache](reference/shoal/cache/index.md){ .layer } [ipc](reference/shoal/ipc/index.md){ .layer } [metrics](reference/shoal/metrics/index.md){ .layer } [diagnostics](reference/shoal/diagnostics/index.md){ .layer }

</div>

<div class="layer-row" markdown>

[payloads: every Discord object, typed and linked to Discord's docs](reference/shoal/payloads/index.md){ .layer .layer-wide }

</div>

<div class="layer-row" markdown>

[core: snowflakes, flags, enums, the codec, clocks and metrics](reference/shoal/core/index.md){ .layer .layer-wide }

</div>

</div>

The [architecture guide](guide/architecture.md) explains what each layer owns.

</section>
