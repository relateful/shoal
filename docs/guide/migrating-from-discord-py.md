# Migrating from discord.py

Shoal keeps discord.py's names wherever they are good, so most concepts carry over directly. The
high-level bot API (models with methods, `commands.Bot`, cogs, hybrid commands, views) is not built
yet; this page covers what exists and is updated as the rest lands.

## Same idea, same name

| discord.py | Shoal |
| --- | --- |
| `discord.Intents.default()` | `shoal.payloads.Intents.default()` |
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
| `await tree.sync()` | `rest.bulk_overwrite_global_application_commands(application_id, commands)` |
| `discord.Interaction` | `ApplicationCommandInteraction`, `ComponentInteraction`, `ModalSubmitInteraction`, `AutocompleteInteraction` |
| `interaction.response.send_message(...)` | `rest.create_interaction_response(id, token, MessageResponse(...))` |
| `interaction.response.defer()` | `DeferredMessageResponse()`, then `edit_original_interaction_response` |
| `interaction.followup.send(...)` | `rest.create_followup_message(application_id, token, ...)` |
| `interaction.response.send_modal(modal)` | `ModalResponse(data=Modal(...))` |
| `discord.ui.Button`, `discord.ui.Select` | `Button`, `StringSelect` and the other select types |
| `ephemeral=True` | `flags=MessageFlags(ephemeral=True)` |
