# Examples

Bots to copy and run, from a ten-line ping bot to a sharded bot with Prometheus and Grafana. Each
folder has its own README with what it shows and how to run it, and every one was run against
Discord.

> [!NOTE]
> Shoal is not on PyPI yet. Each README installs it from this clone with `pip install -e`, using a
> path relative to that folder.

Most examples read `DISCORD_TOKEN` from the environment, and `DISCORD_GUILD_ID` when they have slash
commands: commands synced to one server appear at once, while global commands can take a while.

## Start here

- [hello](hello/): the smallest bot, `ping` → `pong`.
- [slash](slash/): slash commands with options, choices, autocomplete, a group and a context menu.
- [prefix](prefix/): `!commands` with converters, flags, groups, checks, cooldowns and error replies.
- [hybrid](hybrid/): one definition used as both `?command` and `/command`.
- [cogs](cogs/): a bot split into extensions, reloadable while it runs.
- [compat](compat/): a discord.py bot running on Shoal with its imports changed.

## Community bots

- [roles/reactions](roles/reactions/): react to get a role.
- [roles/buttons](roles/buttons/): buttons and a select menu that keep working after a restart.
- [welcome](welcome/): greet new members, give them a role, say goodbye.
- [moderation](moderation/): timeout, kick, ban and purge, with hierarchy checks and a mod log.
- [tickets](tickets/): a form opens a private support channel; staff close it.
- [giveaways](giveaways/): enter with a button, winners drawn on time, even across restarts.
- [polls](polls/): Discord's native polls and a live button vote.
- [starboard](starboard/): messages with enough stars reposted to `#starboard`.
- [leveling](leveling/): experience for chatting, in SQLite, with `/rank` and `/leaderboard`.
- [logs](logs/): edits, deletions, joins, leaves, nickname and role changes in `#logs`.
- [reminders](reminders/): `/remind in 1h30m`, delivered on time.

## Interfaces

- [components](components/): Components V2 layouts with containers, sections and images.
- [forms](forms/): modals with radio buttons, checkboxes, selects and file uploads.
- [paginator](paginator/): long lists split into pages with buttons.
- [emojis](emojis/): the bot's own emojis, uploaded from a folder and used by name.

## Voice

- [voice/music](voice/music/): join, play, queue, skip and leave, end-to-end encrypted.
- [voice/recorder](voice/recorder/): record each speaker to their own Ogg file.
- [voice/messages](voice/messages/): send voice messages with a waveform.

## Without a gateway

- [http](http/): Discord sends interactions to a web server; nothing stays connected.
- [rest](rest/): scripts that post, and send and edit through webhooks, with no bot running.

## At scale

- [bigbot](bigbot/): a project layout for a big bot: metrics with a Grafana dashboard, a cache sized
  for scale, warm restarts, an event loop watchdog, resharding without downtime, under Docker
  Compose.
- [clusters](clusters/): one bot over several processes sharing identify limits, sessions, the shard
  directory, rate limits and the cache through Redis.
- [workers](workers/): the gateway, the bot's logic and REST in separate processes, so deploys never
  drop the shards.
