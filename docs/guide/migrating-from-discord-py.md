# Migrating from discord.py

Shoal keeps discord.py's names wherever they are good, so most bots change their imports and little
else. [Writing a bot](bot.md) shows the whole bot API.

## Same idea, same name

| discord.py | Shoal |
| --- | --- |
| `discord.Client(intents=...)` | `shoal.Client(intents=...)` |
| `commands.Bot("!", intents=...)`, `@bot.command()`, `@bot.hybrid_command()` | the same, from `shoal.commands` |
| `commands.Cog`, `@commands.Cog.listener()`, `bot.load_extension` | the same, from `shoal.commands` |
| `app_commands.CommandTree(client)`, `@tree.command()`, `tree.sync()` | the same, from `shoal.app_commands` |
| `discord.ui.View`, `@ui.button`, `ui.Modal`, `ui.TextInput` | the same, from `shoal.ui` |
| `interaction.response.send_message(..., ephemeral=True)`, `followup.send` | the same |
| `client.wait_for("message", check=..., timeout=...)` | the same |
| `await guild.chunk()`, `await guild.query_members(...)` | the same; `chunk` also drops cached members who left |
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
| `discord.NotFound`, `discord.Forbidden` | `NotFoundError`, `ForbiddenError` | every exception name ends in `Error` (a compatibility layer with discord.py's names is [planned](../roadmap.md)) |
| `AutoShardedClient` identifies one shard per 5 s | `ShardManager` uses `max_concurrency` | much faster startup for large bots |
| Cache lost on restart | snapshots plus resumable sessions | warm restarts |
| `Client.http` (undocumented) | `RestClient` (public, standalone) | dashboards and workers |
| One process | gateway and workers can be split with `shoal.ipc` | scaling and zero-downtime deploys |

## Interactions

Until the command framework lands, these are the building blocks underneath it. The
[interactions guide](interactions.md) covers them in full.

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
