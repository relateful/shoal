# Commands and interactions

Slash commands, buttons, select menus and modals all reach your app as **interactions**. This page
covers the typed building blocks underneath: registering commands, receiving interactions over the
gateway or over HTTP, and answering them. Most bots use the command framework built on them, shown in
[writing a bot](bot.md); this page is for when you want the layer below.

## Registering commands

Describe every command once and overwrite the whole set. Commands left out are deleted, so the list
in your code is always the truth.

```python
from shoal.payloads import (
    ApplicationCommandOption,
    ApplicationCommandOptionType,
    ApplicationCommandType,
    OverwriteCommandParams,
    InteractionContextType,
)

commands = [
    OverwriteCommandParams(
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
    OverwriteCommandParams(name="Report message", type=ApplicationCommandType.MESSAGE),
]
await rest.commands.overwrite_global(application_id, commands)
```

Guild commands (`rest.commands.overwrite_guild`) update instantly and suit development.
Discord applies `contexts` and `integration_types` to global commands only.
`CreateGuildCommandParams` and `EditGuildCommandParams` leave them out, so
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

Answer with `rest.interactions.respond(interaction.id, interaction.token, response)`.

An interaction's repr includes its token, like every other field. Log `interaction.id` rather than
the whole object.

### Over HTTP, without a gateway

An app that only uses commands and components needs no gateway connection. `Endpoint`
(`pip install 'shoal[interactions]'`) checks Discord's Ed25519 signature on every request, answers
`PING` itself, and passes the rest to your handler. Return the response to send it in the HTTP reply,
or return `None` after answering through the callback endpoint yourself. Returning `None` without
answering leaves the interaction unanswered, and Discord shows it as failed.

```python
import asyncio

from shoal.endpoint import Endpoint
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


async with Endpoint(public_key, handle, port=8080):
    await asyncio.Event().wait()
```

Put a TLS reverse proxy in front: Discord only calls HTTPS URLs. A handler that runs longer than
`handler_timeout` (10 seconds by default) is cancelled and answered with a 500.

To serve interactions from an existing aiohttp application, such as a dashboard's backend, call
`server.install(app)` instead of starting the server. The route then shares that application's
settings, including its request body limit (`client_max_size`, 1 MiB by default).

### Webhook events

Discord can also post app-level events to a second URL, the app's Webhook Events URL: an app was
authorized or deauthorized, an entitlement was created, updated or deleted, and Social SDK lobby
and direct messages. Give `Endpoint` an `events` handler and set the URL to its `events_path`
(`/events` by default):

```python
from shoal.core.codec import decode_json
from shoal.payloads import ApplicationAuthorized, WebhookEventPayload


async def events(payload: WebhookEventPayload) -> None:
    event = payload.event
    if event and event.type == "APPLICATION_AUTHORIZED" and event.data:
        authorized = decode_json(event.data, ApplicationAuthorized)
        ...


async with Endpoint(public_key, handle, events=events, port=8080):
    ...
```

The server verifies each request like an interaction, answers the `PING` Discord sends when the URL
is saved, and acknowledges every event with `204` at once, running the handler in its own task:
Discord retries an event not acknowledged within 3 seconds, for up to 10 minutes.
`client.endpoint(public_key)` does this for a `Client`, which emits each event as
`on_<event type>` (`on_application_authorized`, `on_entitlement_create`, ...) with its data.

## Answering

Discord fails an interaction that has no response within **3 seconds**. Each kind of answer is its
own class, so a modal cannot be sent with message data by mistake:

| Response | Use it to |
| --- | --- |
| `MessageResponse` | reply with a message |
| `DeferredMessageResponse` | show "thinking…", then fill it in with `rest.interactions.edit_original` |
| `UpdateMessageResponse` | edit the message a component is on |
| `DeferredUpdateResponse` | acknowledge a component now and edit its message later |
| `AutocompleteResponse` | suggest up to 25 choices, in `AutocompleteChoices` |
| `ModalResponse` | open a form, described by a `Modal` |

When the work may take longer than 3 seconds, defer first. `Endpoint` logs every handler
that takes longer, and records handler time as `shoal_http_interaction_seconds`.

The interaction token stays valid for 15 minutes from when the interaction is received
(`INTERACTION_TOKEN_LIFETIME`). Until then, the app can edit its response and send follow-ups.
These calls go to the application's webhook, so they take `application_id`, not the interaction
id:

```python
from shoal.payloads import SendFollowupParams, MessageFlags

await rest.interactions.send_followup(
    application_id,
    interaction.token,
    SendFollowupParams(content="Done.", flags=MessageFlags(ephemeral=True)),
)
```

`edit_followup` and `delete_followup` take the follow-up's message id as well.

Responses that carry a message (`MessageResponse`, `UpdateMessageResponse`), follow-ups and their
edits take `files=`, as in [Files and images](dashboards.md#files-and-images). Passing files with any
other response raises `TypeError`.
`MessageFlags(ephemeral=True)` shows a message only to the user who acted.

## Components and modals

With a client, build them with `shoal.ui` ([writing a bot](bot.md#buttons-selects-and-modals)):
views and layouts route their interactions back to your methods. Without one, components are typed
structs; the `type` number is never written by hand.

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
