# Writing a bot

This page builds a bot from the top: a `Client` (or `commands.Bot`), slash commands, prefix and
hybrid commands, buttons and modals, cogs and extensions, and the application's emojis. Every name
a bot uses most is also available as `shoal.<Name>`. Complete bots to run and copy, from a ping bot
to a sharded one with Grafana, are in the repository's
[`docs/examples`](https://github.com/relateful/shoal/tree/main/docs/examples).

## A client and its events

```python
import shoal
from shoal.client import Client

client = Client(intents=shoal.Intents.default())


@client.event
async def on_ready() -> None:
    print(f"logged in as {client.user}")


@client.event
async def on_message(message: shoal.Message) -> None:
    if message.content == "ping":
        await message.reply("pong")


client.run("token")
```

`run` logs in, connects every shard Discord recommends and stops cleanly on Ctrl+C. Events arrive as
models (`Message`, `Member`, `Guild`) whose methods call Discord: `message.reply`, `member.add_roles`,
`channel.send`. Reading a message's text needs the Message Content intent:
`Intents.default().with_flags(message_content=True)`, also enabled in the Developer Portal.

`client.wait_for("message", check=..., timeout=30)` waits for the next matching event.

A guild's members are not all sent when it arrives (without the Presence intent, almost none
are). With the Server Members intent the client fetches the member list of each guild that arrives
without it, as the guilds stream in: one guild at a time per shard, waiting out Discord's limit of
one full list per guild every 30 seconds, and each shard counts as ready once its guilds are
chunked. Guilds the bot joins later are chunked too. `chunk_guilds_at_startup=True` without that
intent raises `ValueError`. Large bots often pass `chunk_guilds_at_startup=False` and fetch members
where they need them: `await guild.chunk()` fetches every member over the gateway and drops cached
members who left while the bot was not told; concurrent calls share one request.
`await guild.query_members("ada")` or `query_members(user_ids=[...])` fetches up to 100. A request Discord rate limits fails at once with
`MemberRequestRateLimitedError` and its `retry_after`.
Subclass `Client` and define `on_<event>` methods, or override `setup_hook` to run code after
logging in and before connecting (syncing commands, adding persistent views).

For a large bot, the client takes what the layers below it take: `metrics=` (Prometheus),
`session_store=` and `cache_snapshot=` (warm restarts), `shard_ids=`, `identify_limiter=`,
`shard_directory=`, `command_router=` and `cluster_name=` (clusters), and the shards' connection
settings (`compression=`, `large_threshold=`). See [Scaling](scaling.md) and
[Caching](caching.md).

## Slash commands

```python
from shoal import app_commands
from shoal.app_commands.tree import CommandTree

tree = CommandTree(client)


@tree.command(description="Say hello")
@app_commands.describe(who="Who to greet")
async def hello(interaction: shoal.Interaction, who: shoal.Member) -> None:
    await interaction.response.send_message(f"Hello {who.mention}", ephemeral=True)
```

Parameters become options, with their types read from the annotations; `app_commands.Range`,
`app_commands.choices` and `@command.autocomplete("name")` refine them. Checks such as
`app_commands.checks.has_permissions(manage_messages=True)` and
`app_commands.checks.cooldown(1, 10.0)` go below the command decorator; a cooldown is counted only
when every other check passed. Group subcommands with `app_commands.Group`. Commands are sent to
Discord with `await tree.sync()` (global) or `await tree.sync(guild=...)`, usually from
`setup_hook`.

An interaction is answered once, within 3 seconds: `response.send_message`, `response.defer` (then
`followup.send` or `edit_original_response` for up to 15 minutes), `response.edit_message` on a
component, or `response.send_modal`.

## Prefix and hybrid commands

```python
import random

from shoal import commands

bot = commands.Bot("!", intents=shoal.Intents.default().with_flags(message_content=True))


@bot.command()
async def add(ctx: commands.Context, left: int, right: int) -> None:
    """Add two numbers."""
    await ctx.send(str(left + right))


@bot.hybrid_command()
async def roll(ctx: commands.Context, sides: int = 6) -> None:
    """Roll a die, as !roll or /roll."""
    await ctx.send(str(random.randint(1, sides)))
```

A `Bot` is a `Client` with commands, and has a `bot.tree` for slash commands. Arguments are converted
from their annotations (`int`, `Member`, `TextChannel`, `Greedy[...]`, `Annotated[str, MyConverter]`,
`*words` for every word left, a keyword-only parameter for the rest of the message). Checks, cooldowns
and `max_concurrency` decorate commands; errors reach `on_command_error`. A hybrid command is one
definition used both as `!roll` and as `/roll`; its checks run on both sides, before any option is
converted. The default help command is `!help`.

### Flags, defaults and more conversions

```python
class BanFlags(commands.FlagConverter):
    member: shoal.Member
    reason: str = "No reason"
    days: int = commands.flag(default=1, aliases=["d"], description="Days of messages to delete")


@bot.command()
async def ban(ctx: commands.Context, *, flags: BanFlags) -> None:  # !ban member: @Ada days: 7
    await flags.member.ban(reason=flags.reason, delete_message_seconds=flags.days * 86_400)


@bot.command()
async def avatar(ctx: commands.Context, who: shoal.Member | shoal.User = commands.Author) -> None:
    await ctx.send(who.display_avatar.url)  # !avatar, or !avatar @Ada


@bot.command()
async def say(ctx: commands.Context, *, text: Annotated[str, commands.clean_content()]) -> None:
    await ctx.send(text)  # mentions written as names that ping nobody
```

- `FlagConverter` takes the rest of the message as `name: value` pairs, in any order; a class sets
  its `prefix`, `delimiter` and `case_insensitive`. `list[T]` flags can be given again and again,
  `tuple[...]` flags take several words. In a hybrid command each flag is its own slash option.
- `commands.param()` sets a parameter's default (a function of the context: `Author`,
  `CurrentChannel`, `CurrentGuild`), description, converter and how help shows it.
- Every converter has a class too (`MemberConverter`, `ColourConverter`, `Timestamp`, ...), and an
  `Attachment` parameter takes the message's next attached file.
- `dynamic_cooldown` chooses the limit per user (or guild, ...) from a function; `GroupCog` puts a
  cog's slash commands in one slash group; `MinimalHelpCommand` and `Paginator` change how help looks.

Slash commands can transform options with code of their own (`Transform[Item, ItemTransformer]`, run
after the checks pass) and be translated: `await bot.tree.set_translator(MyTranslator())` sends
every command, option and choice name with its translations on `sync`.

## Cogs and extensions

```python
class Fun(commands.Cog):
    """Games and dice."""

    @commands.hybrid_command()
    async def flip(self, ctx: commands.Context) -> None:
        await ctx.send(random.choice(["heads", "tails"]))

    @commands.Cog.listener()
    async def on_member_join(self, member: shoal.Member) -> None: ...


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fun())
```

`await bot.load_extension("bot.fun")` imports the module and runs its `setup`; `unload_extension`
removes everything it added, its slash commands included, and `reload_extension` puts the old version
back if the new one fails to load. A slash `app_commands.Group` made in a cog's body is copied per cog,
with its subcommands bound to that cog.

## Buttons, selects and modals

```python
from shoal import ui


class Counter(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=60)
        self.count = 0

    @ui.button(label="+1", style=shoal.ButtonStyle.PRIMARY)
    async def add(self, interaction: shoal.Interaction, button: ui.Button) -> None:
        self.count += 1
        button.label = f"+1 ({self.count})"
        await interaction.response.edit_message(view=self)


class Feedback(ui.Modal, title="Feedback"):
    body = ui.TextInput(label="What could be better?")

    async def on_submit(self, interaction: shoal.Interaction) -> None:
        await interaction.response.send_message(f"Thanks: {self.body}", ephemeral=True)
```

A view sent with a message (`channel.send(view=Counter())`, `response.send_message(view=...)`) answers
only on that message, and stops after `timeout` seconds without use; `interaction_check` can refuse an
interaction before anything about the view changes. A persistent view (`timeout=None`, every item with
a `custom_id` you choose) keeps working after a restart once added again with `client.add_view(view)`.
Items are checked against Discord's limits (label and `custom_id` lengths, option counts) before they
are sent. `await interaction.response.send_modal(Feedback())` shows a modal; its `on_submit` runs in
its own task.

### Layouts (Components V2)

A `LayoutView` is the whole message: text, images, sections and containers, with buttons and
selects in action rows among them. It replaces the message's content and embeds, so sending it with
`content` or `embeds` raises `TypeError`.

```python
class Status(ui.LayoutView):
    heading = ui.TextDisplay("## Server status")
    details = ui.Container(
        ui.Section("All systems normal", accessory=ui.Thumbnail("https://example.com/ok.png")),
        ui.Separator(),
        ui.MediaGallery("https://example.com/graph.png"),
        accent_colour=0x57F287,
    )
    row = ui.ActionRow()

    @row.button(label="Refresh", style=shoal.ButtonStyle.PRIMARY)
    async def refresh(self, interaction: shoal.Interaction, button: ui.Button) -> None:
        await interaction.response.send_message("Refreshed", ephemeral=True)


await channel.send(view=Status())
```

Items declared on the class are copied for each view. A method decorated through a row
(`@row.button`, `@row.select`) gets as `self` the class that defines it: the view, or a
`ui.Container` subclass with items of its own; an `ActionRow` subclass can declare buttons with
`@ui.button`, and there `self` is the row. Media is a URL or a `File` sent with the message
(`ui.File(upload)` shows it in place). The message holds at most 40 components, counting those
inside others, and every `id` you give a component must be unique in it.

Modals take more than text: wrap any input in a `ui.Label`.

```python
class Order(ui.Modal, title="Order"):
    note = ui.TextDisplay("Pick your pizza")
    size = ui.Label("Size", ui.RadioGroup(options=[...]))
    toppings = ui.Label("Toppings", ui.CheckboxGroup(options=[...]))
    photo = ui.Label("Inspiration", ui.FileUpload(file_types=["image"], required=False))
    gift = ui.Label("It's a gift", ui.Checkbox())
```

After submission `size.component.value`, `toppings.component.values`, `photo.component.values` (the
uploaded attachments) and `gift.component.value` hold the answers.

## Voice messages

A voice message plays inline with a waveform preview. Send Ogg Opus audio (what Discord's own
clients record); its duration is read from the stream:

```python
from shoal import VoiceMessage

await channel.send(voice_message=await VoiceMessage.from_path("hello.ogg"))
```

A voice message is a single audio attachment: no content, embeds, other files, view, poll or
stickers, and Discord does not let it be edited later. Without a `waveform` the preview is flat;
pass one built with `waveform_of(levels)` from the loudness of each 100 ms of the recording (up to
256 points, each the loudest of the slices it covers). The bot needs the Send Voice Messages
permission in the channel.

## The application's emojis

Upload a folder of images as the application's emojis, then use them by name anywhere:

```bash
DISCORD_TOKEN=... python -m shoal.emojis sync assets/emojis
```

```python
from shoal.emojis import AppEmojis, app_emoji


class Icons(AppEmojis):
    approve = app_emoji("✅")


client = Client(intents=shoal.Intents.default(), app_emojis=Icons())
# Anywhere the client is: client.app_emojis.approve, interaction.client.app_emojis.approve
```

Each declared name has a unicode fallback, used until the emoji is uploaded, so a message never
shows a blank where an icon should be. The sync skips unchanged images and retries what Discord
refused for the moment.
