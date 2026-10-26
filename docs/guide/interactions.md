# Commands and interactions

Slash commands, buttons, select menus and modals all reach your app as **interactions**. This page
covers the typed building blocks: registering commands, receiving interactions over the gateway or
over HTTP, and answering them. A command framework with decorators, checks and cogs is on the
[roadmap](../roadmap.md); everything here is what it will be built on.

## Registering commands

Describe every command once and overwrite the whole set. Commands left out are deleted, so the list
in your code is always the truth.

```python
from shoal.payloads import (
    ApplicationCommandOption,
    ApplicationCommandOptionType,
    ApplicationCommandType,
    BulkApplicationCommandParams,
    InteractionContextType,
)

commands = [
    BulkApplicationCommandParams(
        name="remind",
        description="Remind me about something",
        options=[
            ApplicationCommandOption(
                type=ApplicationCommandOptionType.STRING,
                name="what",
                description="What to remind you about",
                required=True,
            ),
        ],
        contexts=[InteractionContextType.GUILD, InteractionContextType.BOT_DM],
    ),
    BulkApplicationCommandParams(name="Report message", type=ApplicationCommandType.MESSAGE),
]
await rest.bulk_overwrite_global_application_commands(application_id, commands)
```

Guild commands (`bulk_overwrite_guild_application_commands`) update instantly and suit development.
Discord applies `contexts` and `integration_types` to global commands only.
`CreateGuildApplicationCommandParams` and `EditGuildApplicationCommandParams` leave them out, so
creating or editing one guild command cannot set them. Bulk overwrite uses one type for both scopes,
and Discord ignores those fields on guild commands.

## Receiving interactions

Each interaction type is its own class, so `data` is exactly typed after an `isinstance` check:

| Class | When | `data` |
| --- | --- | --- |
| `ApplicationCommandInteraction` | a slash, user or message command was used | `ApplicationCommandData` |
| `AutocompleteInteraction` | the user is typing in an autocomplete option | `ApplicationCommandData` |
| `ComponentInteraction` | a button was pressed or a select changed | `MessageComponentData` |
| `ModalSubmitInteraction` | a modal was submitted | `ModalSubmitData` |
| `PingInteraction` | Discord checking an HTTP endpoint | none |

`parse_interaction` decodes one from JSON. A type newer than your version of Shoal comes back as
`UnknownInteraction`, with its `id` and `token`, instead of an error.

### Over the gateway

```python
from shoal.core.dispatch import DispatchEvent
from shoal.payloads import parse_interaction


async def dispatch(event: DispatchEvent) -> None:
    if event.name == "INTERACTION_CREATE":
        interaction = parse_interaction(event.data)
        ...
```

Answer with `rest.create_interaction_response(interaction.id, interaction.token, response)`.

An interaction's repr includes its token, like every other field. Log `interaction.id` rather than
the whole object.

### Over HTTP, without a gateway

An app that only uses commands and components needs no gateway connection. `InteractionServer`
(`pip install 'shoal[interactions]'`) checks Discord's Ed25519 signature on every request, answers
`PING` itself, and passes the rest to your handler. Return the response to send it in the HTTP reply,
or return `None` after answering through the callback endpoint yourself. Returning `None` without
answering leaves the interaction unanswered, and Discord shows it as failed.

```python
import asyncio

from shoal.interaction_server import InteractionServer
from shoal.payloads import (
    ApplicationCommandInteraction,
    Interaction,
    InteractionMessage,
    InteractionResponse,
    MessageResponse,
    UnknownInteraction,
)


async def handle(interaction: Interaction | UnknownInteraction) -> InteractionResponse | None:
    if isinstance(interaction, ApplicationCommandInteraction) and interaction.data.name == "remind":
        return MessageResponse(data=InteractionMessage(content="I'll remind you."))
    return None


async with InteractionServer(public_key, handle, port=8080):
    await asyncio.Event().wait()
```

Put a TLS reverse proxy in front: Discord only calls HTTPS URLs. A handler that runs longer than
`handler_timeout` (10 seconds by default) is cancelled and answered with a 500.

To serve interactions from an existing aiohttp application, such as a dashboard's backend, call
`server.install(app)` instead of starting the server. The route then shares that application's
settings, including its request body limit (`client_max_size`, 1 MiB by default).

## Answering

Discord fails an interaction that has no response within **3 seconds**. Each kind of answer is its
own class, so a modal cannot be sent with message data by mistake:

| Response | Use it to |
| --- | --- |
| `MessageResponse` | reply with a message |
| `DeferredMessageResponse` | show "thinking…", then fill it in with `edit_original_interaction_response` |
| `UpdateMessageResponse` | edit the message a component is on |
| `DeferredUpdateResponse` | acknowledge a component now and edit its message later |
| `AutocompleteResponse` | suggest up to 25 choices, in `AutocompleteChoices` |
| `ModalResponse` | open a form, described by a `Modal` |

When the work may take longer than 3 seconds, defer first. `InteractionServer` logs every handler
that takes longer, and records handler time as `shoal_http_interaction_seconds`.

The interaction token stays valid for 15 minutes from when the interaction is received
(`INTERACTION_TOKEN_LIFETIME`). Until then, the app can edit its response and send follow-ups.
These calls go to the application's webhook, so they take `application_id`, not the interaction
id:

```python
from shoal.payloads import CreateFollowupMessageParams, MessageFlags

await rest.create_followup_message(
    application_id,
    interaction.token,
    CreateFollowupMessageParams(content="Done.", flags=MessageFlags(ephemeral=True)),
)
```

`edit_followup_message` and `delete_followup_message` take the follow-up's message id as well.

Responses that carry a message (`MessageResponse`, `UpdateMessageResponse`), follow-ups and their
edits take `files=`, as in [Files and images](dashboards.md#files-and-images). Passing files with any
other response raises `TypeError`.
`MessageFlags(ephemeral=True)` shows a message only to the user who acted.

## Components and modals

Components are built from typed structs; the `type` number is never written by hand.

```python
from shoal.payloads import (
    ActionRow,
    Button,
    ButtonStyle,
    Container,
    CreateMessageParams,
    MessageFlags,
    TextDisplay,
)

params = CreateMessageParams(
    flags=MessageFlags(is_components_v2=True),
    components=[
        Container(
            components=[
                TextDisplay(content="**Deploy finished**"),
                ActionRow(components=[Button(style=ButtonStyle.SUCCESS, custom_id="ack", label="Got it")]),
            ]
        )
    ],
)
```

Everything except action rows needs `MessageFlags(is_components_v2=True)`. Modals take `Label`s,
each wrapping one input (`TextInput`, a select, `RadioGroup`, `CheckboxGroup`, `Checkbox` or
`FileUpload`), and `TextDisplay`s for text between them.

Components you **receive** (on a message, or in a modal submission) are kept as plain JSON, so a
component type Discord adds later never stops a message from decoding. Decode them when you need
them. `parse_components` and `parse_submitted_components` return typed components, with
`UnknownComponent` for anything Shoal cannot decode:

```python
from msgspec import UNSET

from shoal.payloads import parse_components, parse_submitted_components

if message.components is not UNSET:
    components = parse_components(message.components)

fields = parse_submitted_components(interaction.data.components)  # a ModalSubmitInteraction
```

## Interaction tokens are credentials

Anyone holding an interaction token can post as your app until it expires. Shoal never writes one to
a log line, an error message or a metric label: routes that contain a token show it as
`{interaction_token}`.
