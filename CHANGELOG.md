# Changelog

All notable changes are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Content scanning flags (Discord, October 28, 2026): `AttachmentFlags` and `EmbedFlags` gain
  `contains_explicit_content`, `contains_gore_content` and `contains_self_harm_content`, and
  `UnfurledMediaItem.content_scan_metadata` carries `ContentScanMetadataFlags`.
- `shoal.tasks`: `tasks.loop` (intervals, times of day, hooks), cron expressions with time zones, and
  `client.scheduler` for jobs at a time, after a delay or on a cron schedule, kept in memory or in
  Redis (`RedisJobStore`: survives restarts, each due job claimed by one process, leased).
- Voice receive decoding: `VoiceClient.audio()` yields PCM per user, reordered, with losses
  concealed, through a small libopus binding (`shoal.voice.receive`); packets from a sender Discord
  has not named yet are held until it does instead of dropped.
- Per-field cache trimming: `CachePolicy(fields=...)` stores only the named fields of a kind.
- `shoal.core`: `Snowflake`, immutable `BaseFlags` bitfields, open enums that accept values Discord adds
  later, the msgspec JSON and msgpack codec, the `Clock` protocol with an interruptible sleep, a shared
  backoff function, owner-only atomic file writes, and the metrics catalog with the `Metrics` protocol.
- `shoal.payloads`: typed payloads, one module per Discord domain (API constants, users, permissions,
  emoji, guilds, channels, messages, voice, gateway, gateway events, rate limits, errors), each linked to
  its section of Discord's docs. Includes message search parameters and results, presences, voice states, reactions and
  thread events, and handling for obfuscated channels (`Channel.is_obfuscated`, `Channel.visible_name`).
- `shoal.rest`: `RestClient` with bot and bearer tokens, typed routes with docs links, per-bucket and
  global rate limiting, the invalid request guard, stop-after-401, and Search Guild Messages with
  retries while Discord builds the index.
- Every HTTP endpoint Discord documents (237), grouped by resource with short names:
  `rest.messages.create`, `rest.members.ban`, `rest.commands.overwrite_global`. The coverage page
  lists the Shoal method for each Discord endpoint. Resources: `applications`, `audit_logs`,
  `automod`, `channels`, `commands`, `emojis`, `entitlements`, `gateway`, `guilds` (prune, widget,
  onboarding, welcome screen and the guild's other settings), `identities`, `interactions`, `invites`,
  `lobbies`, `members` (bans
  included), `messages`, `oauth2`, `polls`, `reactions`, `role_connections`, `roles`,
  `scheduled_events`, `skus`, `soundboard`, `stage_instances`, `stickers`, `subscriptions`,
  `templates`, `threads`, `users`, `voice`, `voice_states` and `webhooks`, each with its payloads. The
  four endpoints Discord has deprecated or disabled are left out.
- Every gateway event Discord documents (82) is typed: `DISPATCH_PAYLOADS` maps each dispatch name
  to the type its data decodes into, and the coverage page lists them. Includes Auto Moderation,
  audit log entries, bans, stickers, integrations, invites, scheduled event subscribers, soundboard
  sounds, polls, typing, voice channel effects and status, voice server updates and `RATE_LIMITED`
  (which the shard logs). Shards send the new Request Soundboard Sounds and Request Channel Info
  commands; `ShardManager.request_soundboard_sounds` splits a guild list across shards.
- The cache holds stickers, scheduled events, stage instances and soundboard sounds, follows poll
  votes, scheduled event subscriber counts and the bot's thread membership, and can be read
  synchronously with `CacheStore.peek` and `peek_scoped` (snapshot format 3; older snapshots are
  ignored and the cache starts cold once).
- File uploads: `File` (bytes, or read off the event loop with `File.from_path`) on every endpoint
  that takes files. Message-like requests describe new files in `attachments` themselves; edits only
  append, so existing attachments are never dropped by accident. `image_data` and `sound_data` build
  the data URIs Discord's image and sound fields take.
- Payloads that hold a credential hide it in their `repr` (`REDACTED_FIELDS`), and invite and
  template codes join tokens among the path values kept out of logs.
- `shoal.gateway`: zlib-stream and zstd-stream decompression, shard routing, `max_concurrency` identify
  scheduling, persistent sessions, heartbeat tracking, the send limiter, event delay tracking, a
  resumable `Shard` that falls back from a failing resume URL to the main gateway, and `ShardManager`
  with cluster assignment (`cluster_shard_ids`).
- `shoal.cache`: per-entity cache policies, per-shard freshness tracking, scope-indexed collections,
  snapshots that line up with resumed sessions, restart strategies, and a `CacheUpdater` that applies
  every cache-relevant gateway event (guilds, channels, threads, roles, emojis, members, users,
  messages, reactions, presences and voice states).
- `shoal.ipc`: `EventServer` and `EventClient` to stream gateway events between processes over TCP, with
  token authentication, optional TLS, event filtering and reconnects.
- Application commands: typed commands, options, choices and permissions, and the 15 live command
  endpoints. Creating or editing one guild command takes its own type, without the global-only
  fields.
- Components: every message and modal component, including Components V2 and the newer modal inputs,
  with layout unions that make invalid nesting a type error. Received components decode lazily
  (`parse_components`), so a component type newer than Shoal never breaks a message.
- Interactions: one class per interaction type and per response type, `parse_interaction` with an
  `UnknownInteraction` fallback, modal submissions, resolved data, and the eight response and
  follow-up endpoints. Interaction tokens never appear in logs, errors or metrics.
- `shoal.endpoint`: receive interactions over HTTP without a gateway, with Ed25519
  signature checks, inline or callback answers, and handler timing against the 3-second deadline
  (`pip install 'shoal[interactions]'`). `client.endpoint(public_key)` serves a client's views,
  modals and commands over HTTP; the first response becomes the HTTP reply.
- `shoal.models`: guilds, members, roles, channels, threads, messages, users, emojis and embeds, with
  synchronous lookups that read the cache (`guild.get_member`, `get_member_named`) and actions that
  call REST (`send`, `edit`, `ban`, `add_roles`, `history`, `typing`).
- `shoal.client`: `Client` with login, sharded connect and `run`; events as models with the earlier
  state read from the cache; raw events that are never dropped; readiness that does not wait for
  member chunking; `wait_for`; interactions with `response` and `followup`.
- `shoal.ui`: `View`, `Modal`, `Button`, the five selects and `TextInput`, with persistent views,
  timeouts and interaction checks.
- `shoal.app_commands`: `CommandTree`, slash commands, groups and context menus with options from type
  hints, autocomplete, checks, cooldowns, error handlers and sync; Discord's limits are checked where
  the decorator is written.
- `shoal.emojis`: the application's emojis by name (`client.app_emojis.approve`), loaded at login,
  with declared names and unicode fallbacks, and a sync from a folder of images (in the bot, or
  `python -m shoal.emojis sync`) that skips unchanged images and never re-uploads what it lost track of.
- `shoal.commands`: prefix and hybrid commands. `Bot` (a `Client` with commands and a slash command
  tree), `Context`, commands and groups with argument conversion from type hints (`Greedy`, `*words`,
  the rest of the message, converters), checks, cooldowns and `max_concurrency`, cogs with listeners,
  extensions that load, unload and reload (taking their slash commands with them), a help command,
  and hybrid commands and groups used both as `!name` and `/name`, with their checks run on both
  sides before any option is converted.
- `shoal.core.cooldown`: one sliding-window cooldown for both command frameworks, which can be asked
  how long to wait without recording a use (`get_retry_after`).
- `Client` options for large bots: `metrics`, `session_store`, `cache_snapshot` (loaded before
  connecting, saved after the shards close), `identify_limiter`, `clock`, and the shards' connection
  settings (`compression`, `large_threshold`, `capabilities`, ...). `commands.Bot` takes them too.
- The most used names at the top level (`shoal.Client`, `shoal.Embed`, `shoal.app_commands`), loaded
  on first use, so importing one layer still loads nothing else.
- `guild.chunk()` and `guild.query_members()`: members over the gateway. Concurrent `chunk()` calls
  share one request, the cache drops members who are not in the full list, and a request Discord rate
  limits fails at once (`MemberRequestRateLimitedError`).
- `chunk_guilds_at_startup`: with the Server Members intent, every guild that arrives without its
  member list is chunked as it streams in, one guild at a time per shard, retrying after
  `RATE_LIMITED`; each shard is ready once its startup guilds are chunked, and joined guilds are
  chunked too. On by default with that intent; pass `False` to chunk on demand.
- `docs/examples/`: bots to copy and run, from a one-file ping bot to a big bot with Prometheus and
  Grafana, each tested against Discord.
- `shoal_events_dropped_total`: gateway payloads and dispatches dropped because they did not decode.
- Webhook events: every event Discord posts to an app's Webhook Events URL is typed
  (`WebhookEventPayload`, `WEBHOOK_EVENT_PAYLOADS`), and `Endpoint(..., events=handler)` receives them,
  acknowledging each at once. `client.endpoint()` emits them as events (`on_application_authorized`,
  `on_entitlement_create`, `on_lobby_message_create`, ...). `shoal_http_webhook_events_total` counts
  them.
- Components V2 in `shoal.ui`: `LayoutView` (the whole message), `ActionRow` (with `@row.button`
  and `@row.select`), `Container`, `Section`, `TextDisplay`, `Thumbnail`, `MediaGallery`, `File` and
  `Separator`; items declared on a view or container class are copied per instance. Modals take
  `Label`s around any input, `TextDisplay`s, and the new `FileUpload`, `RadioGroup`, `CheckboxGroup`
  and `Checkbox`. Every documented limit is checked before sending, and a Components V2 message sent
  with content, embeds, a poll or stickers raises `TypeError`.
- `File.uri`: the `attachment://` reference embeds and components use for a file sent with them
  (with the `SPOILER_` prefix a spoiler file is uploaded under).
- `pip install "shoal[all]"` installs every optional dependency.
- `shoal.compat`: familiar names for migrating bots (`import shoal.compat as discord`): the error
  names without `Error` (`Forbidden`, `commands.MissingRequiredArgument`), renamed types under their
  old names, `compat.utils` (`get`, `find`, `oauth_url`, `snowflake_time`, `as_chunks`, ...).
- Prefix commands: `FlagConverter` and `flag()` (also as hybrid options), `param()` with context
  defaults (`Author`, `CurrentChannel`, `CurrentGuild`) and descriptions, `clean_content`, a converter
  class for every conversion and new ones for colours, invites, stickers, scheduled events, soundboard
  sounds and timestamps, `Attachment` parameters, `run_converters`, `dynamic_cooldown`,
  `bot_has_any_role`, `GroupCog`, `MinimalHelpCommand`, `Paginator` and `AutoShardedBot`.
- Slash commands: `Transformer` and `Transform` (run after the checks), `Translator` and `locale_str`
  (localized names and descriptions on `sync`), `dynamic_cooldown`, and `guild_install`,
  `user_install`, `dm_only` and `private_channel_only`. New errors: `CommandAlreadyRegisteredError`,
  `CommandLimitReachedError`, `CommandSignatureMismatchError`, `CommandSyncFailureError` and
  `MissingApplicationIDError`, each a subclass of what was raised before.
- `shoal.core.formatting`: `escape_markdown`, `remove_markdown`, `escape_mentions`, `format_dt` and the
  mention and timestamp patterns; `Message.clean_content`.
- `PrivilegedIntentsRequiredError`: the gateway's close for intents the application has not enabled,
  saying where to enable them.
- `interaction.namespace` is typed (`OptionNamespace`), so `interaction.namespace.member` type-checks.
- `shoal.redis` (`shoal[redis]`): state shared by a bot's processes. `RedisIdentifyLimiter` and
  `RedisSessionStore` for clusters, `RedisRateLimiter` (route buckets, the global limit and the
  invalid request window counted across processes) and `RedisCollections` for a cache in Redis.
  `CacheStore(collections=...)` takes any `CollectionFactory`.
- Events through a Redis stream (`RedisEventStream`, `RedisEventConsumer`): a broker for IPC, with
  consumer groups that share the events and read again what a crashed worker left unfinished.
- IPC over Unix sockets: `EventServer(path=...)` and `EventClient.unix(path, ...)`.
- Cluster coordination: a `ShardDirectory` where every `ShardManager` reports its shards, and a
  `CommandRouter` that sends a gateway command on the shard of its guild whichever cluster runs it
  (`ShardManager.send_command`, `send_to_guild`); in memory and in Redis (`RedisShardDirectory`,
  `RedisCommandRouter`). `Client` takes them as `shard_directory=` and `command_router=`, and
  `Client.shard_manager` reaches the shards.
- Voice messages: `send(voice_message=VoiceMessage.from_ogg(...))` on channels, replies, contexts,
  interaction responses and follow-ups, with the duration read from the Ogg Opus stream and
  `waveform_of` for the preview; `File` carries `duration` and `waveform` into the attachment.
- Voice (`shoal[voice]`): `await channel.connect()` joins a voice channel and returns the guild's
  `VoiceClient`, which plays (`OggOpusSource`, `FFmpegSource`), pauses, moves and listens
  (`listen()`), and joins again by itself when the session is lost. Calls are end-to-end encrypted
  with DAVE (through `davey`); packets are sealed with AES-256-GCM or XChaCha20-Poly1305. The voice
  gateway (v8, buffered resume), IP discovery and the payloads are in `shoal.voice` and
  `shoal.payloads.voice_gateway`; `shoal.core.ogg` reads and writes Ogg Opus.
- Resharding without downtime: `ShardManager.reshard` and `Client.reshard` start the new shard count
  beside the old one and switch in every cluster once all of it is ready.
- `RestProxy`: one process holds a bot's token and rate limits, and every other process sends REST
  through it with only the proxy's secret (`RestClient(None, base_url=..., proxy_secret=...)`).
  `RouteTable` finds the documented route of a method and path; `rate_limit_of` reads a response's
  rate limits.
- `GatewayRequiredError` and `MemberRequestRateLimitedError` are exported from `shoal.models`.
- `CollectionFactory.shared` and `CacheStore.resharded()`: a store over shared collections numbers
  its writes on from the clock and keeps no snapshots; after a reshard, entries keep their freshness.
- `shoal.metrics.prometheus`: `PrometheusMetrics`, exporting every metric in the catalog.
- `shoal.diagnostics`: `LoopMonitor`, which names the code blocking the event loop while it blocks.
- Documentation site with generated API reference, guides (including writing a bot), and a Discord
  API coverage page checked weekly against Discord's docs.

### Changed

- `SessionStore.delete` takes the shard count too, and sessions are kept per shard count
  (`FileSessionStore` writes `shard-<count>-<id>.json`), so a reshard's two shard counts never
  overwrite each other's sessions. Session files from earlier versions are not read: each shard
  identifies once after upgrading.
- A shard builds its identify once it holds its identify slot, so a presence set while it waited
  goes out with it.
- `Context.reply` takes every keyword `Context.send` does.

- `ui.Item` is the base of every component; the custom ID, `row` and callbacks moved to
  `ui.InteractiveItem`. `TextInput.to_component()` is the bare input (a modal puts it in a label),
  and its `label` is optional inside a `ui.Label`.
- A slash command missing a required option, or sent one it does not have, raises
  `CommandSignatureMismatchError` (sync the tree) instead of `TransformerError`.
- `to_partial_emoji` raises `PartialEmojiConversionFailureError` and `to_object`
  `ObjectNotFoundError`; both are still `BadArgumentError`s.
- Renamed for the naming rules: `rest.channels.set_voice_status` is `edit_voice_status`
  (`EditVoiceStatusParams`), `rest.guilds.edit_widget` is `edit_widget_settings`
  (`EditWidgetSettingsParams`), `BulkLobbyMemberParams` is `BulkEditLobbyMemberParams` and
  `EditRoleConnectionParams` is `EditCurrentRoleConnectionParams`. `Cooldown.retry_after` is
  `update_rate_limit`. `GATEWAY_DOMAIN` moved to `shoal.gateway.defaults`.
- `~flags` inverts all 64 bits, so `permissions & ~other` keeps bits Discord added that Shoal does not
  know yet; it used to clear them.
- A view sent with `response.send_message` answers only on the message it was sent with, and views and
  modals are forgotten as soon as they stop. A user has at most five modals waiting; opening another
  stops the oldest.
- An interaction counts as answered only once Discord accepted the response, so a failed response can
  be sent again. Over HTTP, code after the response runs once the reply is written.
- Channels from `GUILD_CREATE` get their guild's ID when Discord leaves it out.
- Offline presences are not cached (an absent presence reads as offline).
- A close code that ends the session backs off before identifying again, as other failures do.
- `edit(attachments=...)` on messages is the list of attachments to keep, as existing `Attachment`s
  and new `File`s; attachments left out are removed. Leaving it out still keeps them all.
- `max_rate_limit_wait` also bounds the wait before sending (an empty bucket, a global pause, the
  invalid request guard): a longer wait raises `RateLimitedError` at once instead of sleeping.
- A 429 whose JSON body says `global` pauses every route, even without the `X-RateLimit-Global`
  header.
- `Guild.get_user` is removed; use `Client.get_user`. `shoal.models.channel.resolve_guild_channel`
  is `resolve_cached_channel` (it also returns DM channels).
- `Client.connect()` takes the token `login` used when none is given.
- Cache snapshots record the shard count; `load_snapshot(shard_count=...)` starts cold after
  resharding. `Client(cache_snapshot=...)` passes it.
- `Identify`, `Resume` and the IPC `EventFrame` keep the token out of their repr, and `User` keeps its
  email out of it.
- The IPC client resets its reconnect backoff only after a subscription lasted a minute, so a worker
  dropped as too slow over and over backs off.
