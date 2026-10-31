# Caching and restarts

Shoal caches by default, like discord.py, but every part is configurable and the cache survives a
restart without serving stale data as if it were current.

## Policies

Each entity kind (`CHANNEL`, `EMOJI`, `GUILD`, `MEMBER`, `MESSAGE`, `PRESENCE`, `ROLE`,
`SCHEDULED_EVENT`, `SOUNDBOARD_SOUND`, `STAGE_INSTANCE`, `STICKER`, `USER`, `VOICE_STATE`) has a
`CachePolicy`:

```python
from shoal.cache import CacheConfig, CachePolicy, CacheStore, EntityKind

store = CacheStore(
    CacheConfig(
        policies={
            EntityKind.PRESENCE: CachePolicy.disabled(),
            EntityKind.MEMBER: CachePolicy(max_entries=500_000, ttl=3600),
        }
    )
)
```

| Option | Meaning |
| --- | --- |
| `enabled` | cache this kind at all |
| `max_entries` | least recently used entries are evicted beyond this |
| `ttl` | seconds after which an entry is dropped when read |
| `persist` | include the kind in snapshots |
| `fields` | cache only these fields; the rest are reset to their defaults |

### Caching only some fields

```python
CachePolicy(fields=frozenset({"name", "topic", "parent_id"}))  # for EntityKind.CHANNEL
```

With `fields`, every other field of the kind's values is reset to its default before it is stored,
usually `UNSET` (not known), so memory, Redis and snapshots hold only what the bot reads. Fields
Discord always sends, and the fields that say what an object is and where it belongs (`id`, `type`,
`guild_id`, `channel_id`, `user`, `user_id`), are always kept. A name the cached struct does not
have raises `ValueError` when the store is created, so a typo fails at startup. A snapshot saved
under a policy that kept more is trimmed as it loads.

Processes sharing one Redis cache should share one policy: values are trimmed when written, so
a process that keeps fewer fields strips them for every reader, and widening `fields` fills the
new fields in only as Discord sends each object again.

Shoal's models compute from the cache: trimming `permission_overwrites` or a member's `roles`, for
example, makes permission checks see none. Keep what the features you use read, or ask Discord:
`guild.fetch_permissions(member)` and `channel.fetch_permissions(member)` cost a request but need no cache.

By default everything is cached. Messages are bounded to 1,000 and users to 100,000 (message authors
from every guild pass through them); the other kinds mirror what Discord says the bot's guilds
contain. Messages and presences are not persisted.

## Freshness

Every entry records its source (`GATEWAY`, `REST` or `SNAPSHOT`), when it was observed, and the shard
that delivered it. When a shard starts a new gateway session, everything that shard delivered before
becomes **stale** until Discord confirms it again. Other shards are not affected: one shard
re-identifying never makes the rest of the cache stale.

```python
member = await store.get_member(guild_id, user_id)  # fast: may be stale
member = await store.get_member(guild_id, user_id, fresh_only=True)  # confirmed this session
```

Every kind has a lookup: `get_channel`, `get_emoji`, `get_guild`, `get_member`, `get_message`,
`get_presence`, `get_role`, `get_scheduled_event`, `get_soundboard_sound`, `get_stage_instance`,
`get_sticker`, `get_user` and `get_voice_state`.

## Reading without `await`

The lookups above are async because a cache can live outside the process (Redis, a database) and be
shared by several shards. `peek` reads what this process holds, synchronously, for code that cannot
await, like discord.py's `guild.get_member(...)`:

```python
member = store.peek(store.members, (guild_id, user_id))
channels = store.peek_scoped(store.channels, guild_id)  # every cached channel of the guild
```

Both take `fresh_only` and count in the lookup metrics like the async reads. With the in-memory
collections (the default) they see everything; a collection backed by a remote store answers them
from a local copy it keeps, or with nothing.

## Sharing the cache across processes

`CacheStore(collections=...)` chooses where each kind is stored. `shoal.redis` stores them in Redis
(install `shoal[redis]`), so gateway processes write what workers and a dashboard read:

```python
from redis.asyncio import Redis
from shoal.redis import RedisCollections

store = CacheStore(config, collections=RedisCollections(Redis.from_url("redis://localhost")))
```

Each entry is its own key, expiring as its kind's `ttl` says, indexed per kind and per guild so
guild-wide work (reconciling, forgetting a guild) reads only that guild's entries. The indexes drop
an entry when it expires, is deleted or moves to another guild, each change in one step, so no
process ever sees an entry missing from its guild. `peek` answers from a local copy of what this
process last read or wrote, bounded by the kind's `max_entries`.

- Redis's own memory limit bounds what it keeps: use the `noeviction` or a `volatile-*` eviction
  policy, so Redis never evicts an index.
- Create the Redis client without `decode_responses`: entries are binary.
- Run one Redis (or a replicated one behind Sentinel), not Redis Cluster: each change touches
  several keys at once.
- The cache outlives the process already, so the store saves and loads no snapshots, and numbers
  its writes on from the clock: a restarted process never writes below what is stored.
- Two processes writing one entry at the same moment keep the last write: let one process (the
  gateway's) run the `CacheUpdater`.

## Warm restarts

```python
await manager.close()  # saves every shard's session
# then the cache, so both end at the same event
await store.save_snapshot("cache.msgpack", shard_count=manager.shard_count)

await store.load_snapshot("cache.msgpack", shard_count=shard_count)  # on start: every entry stale
```

A snapshot saved with a different `shard_count` is not loaded: after resharding no session can
resume, and its entries belong to shards that no longer exist. `Client(cache_snapshot=...)` passes
the shard count both ways.

Save the snapshot **after** closing the shards. The snapshot records the last event it applied from
each shard, and the session file records where Discord will resume; when they line up, snapshot plus
replay is exact. After loading, each shard settles on its own:

- **It resumes its session** (see [scaling](scaling.md)). Discord replays the missed events and
  `RESUMED` arrives. If the replay starts right after the snapshot's last event, the shard's restored
  entries become fresh. If it does not (the snapshot was saved earlier or later), they stay stale and
  are replaced as events update them, and a warning says so.
- **It identifies a new session.** Each `GUILD_CREATE` replaces that guild's data and removes what no
  longer exists. Call `store.sweep_stale()` once every shard is ready to drop what is left: guilds the
  bot left while it was offline. Guilds in an outage are kept.

Either way the bot answers from the snapshot during startup instead of from an empty cache. The
snapshot is written atomically and readable only by the bot's user; it holds member, user and guild
data, so treat it like the database it is. To ignore snapshots, start cold:

```python
store = CacheStore(CacheConfig(restart=RestartStrategy.COLD))
```

## Keeping it in sync

```python
from shoal.cache import CacheUpdater

updater = CacheUpdater(store, intents=intents)
shard = Shard(..., intents=intents, dispatch=updater.apply)
```

`CacheUpdater.handled_events` lists every event it applies. Pass the shards' intents: `GUILD_CREATE`
lists every member only with the `guild_presences` intent and only for guilds that are not large, and
presences only with that intent and up to 75,000 members. The updater removes members and presences
that disappeared only when the event listed them all; otherwise they are kept until member events or
chunking update them. Without `intents` it never assumes a complete list. Partial events (reactions,
pins, thread member counts, and member or guild updates merged into an entry that is not fresh)
change a cached entry without making it fresh: they confirm only what they change. Archived threads
leave the cache, like deleted ones. Deleting a channel also removes its threads and cached
messages; deleting a role removes it from cached members.

Stickers, scheduled events, stage instances and soundboard sounds arrive with `GUILD_CREATE` and
follow their own events. `GUILD_STICKERS_UPDATE` and `SOUNDBOARD_SOUNDS` (the answer to
`ShardManager.request_soundboard_sounds`) replace a guild's whole list; scheduled event subscriber
counts follow `GUILD_SCHEDULED_EVENT_USER_ADD` and `_REMOVE` when the count is known; poll votes
update a cached message's poll results when they are known. The bot's own thread membership
(`Channel.member`) follows `THREAD_MEMBER_UPDATE` and `THREAD_MEMBERS_UPDATE`, which also caches the
guild member and presence of each added thread member.

Cached guilds are `CachedGuild`: a `Guild` plus `joined_at`, `large` and `member_count`, which only
`GUILD_CREATE` sends. Their `roles`, `emojis` and `stickers` lists are empty: those live in their
own collections, so each object is cached once. They are kept across `GUILD_UPDATE` and restarts, and `member_count` follows
joins and leaves.

## Obfuscated channels

From November 16, 2026 Discord sends channels the bot cannot view with their metadata hidden. The
cache stores them as sent; check `Channel.is_obfuscated` and use `Channel.visible_name`. Only `id`,
`type`, `position` and `parent_id` are reliable on such a channel.
