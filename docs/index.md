---
template: home.html
title: Shoal
description: A fully typed Discord API library for Python, built for bots that grow.
hero_title: From one server to a <em>million</em>, without a rewrite.
hero_lead: >-
  Shoal is a fully typed Discord library for Python. Start with one process and one shard; when the
  bot grows, split the gateway, the cache and your code across processes and machines with the same
  objects you started with.
primary_label: Read the guide
primary_link: guide/architecture/
secondary_label: Browse the API
secondary_link: reference/shoal/
---

<div class="stats" markdown>
<p><strong>237</strong><span>HTTP endpoints, every one Discord documents</span></p>
<p><strong>82</strong><span>gateway events, typed</span></p>
<p><strong>16×</strong><span>faster start-up at 512 shards, 16 identifying at once</span></p>
<p><strong>0</strong><span>restarts to change the shard count</span></p>
</div>

<section class="block" markdown>

<p class="eyebrow">Why Shoal</p>

## Built for the day the bot <em>outgrows</em> one process.

<div class="features" markdown>

<div class="feature" markdown>
<span class="feature-index">01</span>
### Starts fast

Shards identify as many at a time as Discord allows, not one every five seconds.
</div>

<div class="feature" markdown>
<span class="feature-index">02</span>
### Survives restarts

Sessions resume after a deploy, and the cache comes back from a snapshot.
</div>

<div class="feature" markdown>
<span class="feature-index">03</span>
### Splits across processes

Gateway processes stream events to workers; clusters share state through Redis.
</div>

<div class="feature" markdown>
<span class="feature-index">04</span>
### Keeps the IP safe

Invalid requests are counted and held back before Cloudflare's ban, and requests stop after a 401.
</div>

<div class="feature" markdown>
<span class="feature-index">05</span>
### Shows what is wrong

Prometheus metrics for every layer, and the line that blocked the event loop.
</div>

<div class="feature" markdown>
<span class="feature-index">06</span>
### Typed to Discord's docs

Every payload follows Discord's field tables, with `UNSET` kept apart from `None`.
</div>

</div>

</section>

<section class="block" markdown>

<p class="eyebrow">Coming from discord.py</p>

## The names you know. The <em>limits</em> you don't.

<div class="compare" markdown>

<div class="compare-row" markdown>
<p class="compare-when">512 shards start</p>
<p class="compare-old">About 43 minutes</p>
<p class="compare-new">Under 3 minutes</p>
</div>

<div class="compare-row" markdown>
<p class="compare-when">You deploy</p>
<p class="compare-old">Every shard identifies again; the cache starts empty</p>
<p class="compare-new">Shards resume; the cache is restored</p>
</div>

<div class="compare-row" markdown>
<p class="compare-when">The event loop blocks</p>
<p class="compare-old">A warning after 10 seconds</p>
<p class="compare-new">The blocking line, within a quarter of a second</p>
</div>

<div class="compare-row" markdown>
<p class="compare-when">The token is revoked</p>
<p class="compare-old">Failing requests count towards an IP ban</p>
<p class="compare-new">Requests stop after the first 401</p>
</div>

<div class="compare-row" markdown>
<p class="compare-when" markdown="span">You need the REST API alone</p>
<p class="compare-old" markdown="span">The undocumented `Client.http`</p>
<p class="compare-new" markdown="span">`RestClient`, public and standalone</p>
</div>

</div>

<p class="block-foot" markdown>`import shoal.compat as discord` keeps the old names while you move. [Read the migration guide](guide/migrating-from-discord-py.md){ .arrow-link }</p>

</section>

<section class="block" markdown>

<p class="eyebrow">One library</p>

## From a script to a <em>fleet</em>.

<div class="code-pair" markdown>

<div class="code-card" markdown>
<p class="code-card-title"><span>script.py</span><span>REST only, no gateway</span></p>

```python
from shoal.payloads import CreateMessageParams
from shoal.rest import RestClient, Token

async with RestClient(Token.bot(token)) as rest:
    me = await rest.users.get_me()
    await rest.messages.create(
        channel_id,
        CreateMessageParams(content=f"hello from {me.username}"),
    )
```
</div>

<div class="code-card" markdown>
<p class="code-card-title"><span>bot.py</span><span>thousands of guilds</span></p>

```python
manager = ShardManager(
    token=token,
    intents=intents,
    dispatch=CacheUpdater(store, intents=intents).apply,
    shard_count=gateway.shards,
    identify_limiter=LocalIdentifyLimiter(16),
    session_store=FileSessionStore("sessions/"),
)
await manager.run()
```
</div>

</div>

</section>

<section class="closing" markdown>

## Start with one shard.

<p class="closing-lead">The same objects carry the bot from its first server to its millionth.</p>

<p class="closing-actions" markdown>[Write your first bot](guide/bot.md){ .button } [Browse the examples](https://github.com/relateful/shoal/tree/main/docs/examples){ .button .button-quiet }</p>

</section>
