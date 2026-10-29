# Migrating from discord.py

Shoal keeps discord.py's names wherever they are good, so most bots change their imports and little
else. [Writing a bot](bot.md) shows the whole bot API.

## Moving over step by step

`shoal.compat` holds the names discord.py code is written with, so a bot can switch its imports first
and rename later:

```python
import shoal.compat as discord
from shoal.compat import app_commands, commands

try:
    await member.send("hi")
except discord.Forbidden:  # shoal.rest.errors.ForbiddenError
    ...


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):  # MissingRequiredArgumentError
        ...
```

Everything in it is the same object as in Shoal: `discord.Member` is `shoal.Member`, and every error
name without `Error` is the error with it. Renamed things keep their old names here too
(`discord.Status` is `StatusType`, `discord.ScheduledEvent` is `GuildScheduledEvent`), and
`discord.utils` has `get`, `find`, `oauth_url`, `snowflake_time`, `format_dt` and the markdown
helpers. New code reads better with Shoal's own names.

Most of the `ext.commands` and `app_commands` surface is there: `FlagConverter` and `flag()`,
`commands.param()` with `Author`, `CurrentChannel` and `CurrentGuild`, `clean_content`, every
converter class (`MemberConverter`, `ColourConverter`, `Timestamp`, ...), `Attachment` parameters,
`dynamic_cooldown`, `GroupCog`, `MinimalHelpCommand` and `Paginator`; `app_commands.Transformer` and
`Transform`, `Translator` and `locale_str`, and `guild_install`, `user_install`, `dm_only` and
`private_channel_only`.

### What compat covers

`shoal.compat` has 439 of the 503 names discord.py 2.8 exports. A test checks it against a snapshot
of those names, so a gap shows up in CI rather than in a bot.

| Package | Names in compat |
| --- | --- |
| `discord` | 208 of 253 |
| `discord.ext.commands` | 142 of 147 |
| `discord.app_commands` | 49 of 60 |
| `discord.ui` | 26 of 27 |
| `discord.ext.tasks` | 1 of 1 |
| `discord.utils` | 13 of 15 |

A name is in compat only when Shoal's object is the same Discord object, so some familiar names
point at Shoal's payloads: the `Raw*Event` names are the gateway event payloads, whose fields use
Discord's names (`MessageDelete.id`, not `message_id`), and `FFmpegPCMAudio` is `FFmpegSource`,
which takes its options as lists of arguments.

The rest is not there yet. The ones a bot is most likely to meet:

- `PermissionOverwrite`: Shoal's `Overwrite` is Discord's allow and deny payload, not a builder
  that takes one argument per permission.
- `Webhook`, `WebhookMessage` and `SyncWebhook`: webhooks are `rest.webhooks` calls, with no
  webhook object that sends.
- `Colour` and `Color`: embed colours are plain integers.
- `ui.DynamicItem`, `utils.sleep_until` and `utils.setup_logging`.
- Voice sources beyond `AudioSource` and `FFmpegSource`: `PCMAudio`, `PCMVolumeTransformer`,
  `FFmpegOpusAudio`.

## Same idea, same name

| discord.py | Shoal |
| --- | --- |
| `discord.Client(intents=...)` | `shoal.Client(intents=...)` |
| `commands.Bot("!", intents=...)`, `@bot.command()`, `@bot.hybrid_command()` | the same, from `shoal.commands` |
| `commands.Cog`, `@commands.Cog.listener()`, `bot.load_extension` | the same, from `shoal.commands` |
| `app_commands.CommandTree(client)`, `@tree.command()`, `tree.sync()` | the same, from `shoal.app_commands` |
| `discord.ui.View`, `@ui.button`, `ui.Modal`, `ui.TextInput` | the same, from `shoal.ui` |
| `ui.LayoutView`, `ui.Container`, `ui.Section`, `ui.TextDisplay`, `@row.button` | the same, from `shoal.ui` |
| `ui.Label`, `ui.FileUpload`, `ui.RadioGroup`, `ui.CheckboxGroup`, `ui.Checkbox` | the same, from `shoal.ui` |
| `interaction.response.send_message(..., ephemeral=True)`, `followup.send` | the same |
| `client.wait_for("message", check=..., timeout=...)` | the same |
| `await guild.chunk()`, `await guild.query_members(...)` | the same; `chunk` also drops cached members who left |
| `chunk_guilds_at_startup=False` | the same; chunking runs one guild at a time per shard, as guilds arrive |
| `discord.Intents.default()` | `shoal.Intents.default()` |
| `discord.Permissions(manage_guild=True)` | `shoal.payloads.Permissions(manage_guild=True)` |
| `perms.manage_guild` | `perms.manage_guild` |
| `discord.utils.snowflake_time(id)` | `Snowflake(id).created_at` |
| `discord.AllowedMentions.none()` | `shoal.payloads.AllowedMentions.none()` |
| `max_messages=1000` | `CachePolicy(max_entries=1000)` for `EntityKind.MESSAGE` |

## Different on purpose

| discord.py | Shoal | Why |
| --- | --- | --- |
| A missing field and `null` both become `None` | `UNSET` (absent) and `None` (null) | updates can tell "leave it" from "clear it" |
| `discord.NotFound`, `discord.Forbidden` | `NotFoundError`, `ForbiddenError` | every exception name ends in `Error` (`shoal.compat` has the old names) |
| `AutoShardedClient` identifies one shard per 5 s | every `Client` shards, identifying `max_concurrency` at once | much faster startup for large bots |
| `commands.param(description=...)` without a default | `Annotated[str, commands.param(description=...)]` | the annotation stays the parameter's real type for type checkers |
| `commands.clean_content` annotation | `Annotated[str, commands.clean_content()]` reads as a `str` | the same, typed |
| Cache lost on restart | snapshots plus resumable sessions | warm restarts |
| `Client.http` (undocumented) | `RestClient` (public, standalone) | dashboards and workers |
| One process | gateway and workers can be split with `shoal.ipc` | scaling and zero-downtime deploys |
| `FFmpegPCMAudio`, `FFmpegOpusAudio` | `FFmpegSource` (encodes to Opus), `OggOpusSource` | Shoal sends Opus as encoded and needs no audio library |
| `discord.ClientException` when already playing | `AudioPlayingError` (a `ShoalError`, not a `ClientError`) | voice sits below the client, so its errors cannot derive from the client's |
| `discord.ext.tasks.loop` | `shoal.tasks.loop` (also `shoal.compat.tasks`): intervals, times of day, `count`, the hooks and `change_interval`; no `reconnect`, so an iteration that raises ends the loop (catch network errors yourself). `client.scheduler` for jobs that survive restarts | built in ([loops and scheduled jobs](tasks.md)) |
| No built-in voice receive | `voice.listen()` yields decrypted Opus packets, `voice.audio()` decoded PCM | built in, with end-to-end encryption ([voice](voice.md)) |

## Without a client

The bot API is built on these, and they work alone: a dashboard or a worker can answer interactions
with no client at all. The [interactions guide](interactions.md) covers them in full.

| discord.py | Shoal |
| --- | --- |
| `await tree.sync()` | `rest.commands.overwrite_global(application_id, commands)` |
| `discord.Interaction` | `ApplicationCommandInteraction`, `ComponentInteraction`, `ModalSubmitInteraction`, `AutocompleteInteraction` |
| `interaction.response.send_message(...)` | `rest.interactions.respond(id, token, MessageResponse(...))` |
| `interaction.response.defer()` | `DeferredMessageResponse()`, then `rest.interactions.edit_original` |
| `interaction.followup.send(...)` | `rest.interactions.send_followup(application_id, token, ...)` |
| `interaction.response.send_modal(modal)` | `ModalResponse(data=Modal(...))` |
| `discord.ui.Button`, `discord.ui.Select` | `Button`, `StringSelect` and the other select types |
| `ephemeral=True` | `flags=MessageFlags(ephemeral=True)` |
