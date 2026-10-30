"""Shoal: a fully typed Discord API library for bots of every size.

    import shoal

    client = shoal.Client(intents=shoal.Intents.default())

The names a bot uses most are here, as `shoal.Client`, `shoal.Embed` or `shoal.app_commands`.
They load on first use, so `import shoal.rest` alone never loads the gateway or the bot layers.

The package is split into layers that can be used on their own:

- `shoal.core`: dependency-free primitives (snowflakes, flags, enums, the codec).
- `shoal.payloads`: typed mirrors of every Discord JSON object, one module per docs page.
- `shoal.rest`: the HTTP client, rate limiter and REST proxy, usable without a gateway.
- `shoal.gateway`: shards, compression, identify scheduling and resumable sessions.
- `shoal.cache`: a policy-driven cache that survives restarts and knows how fresh each entry is.
- `shoal.ipc`: streams gateway events from gateway processes to worker processes.
- `shoal.metrics`: exporters for the metrics every layer records (Prometheus).
- `shoal.diagnostics`: event loop health (`LoopMonitor`).
- `shoal.endpoint`: receives interactions over HTTP, for bots without a gateway.
- `shoal.tasks`: background loops, and jobs scheduled for a time or on a cron schedule.
- `shoal.redis`: what a bot's processes share: limits, sessions, cache, events, shard directory.
- `shoal.voice`: voice connections, end-to-end encrypted, and the audio they play.
- `shoal.models`: `Guild`, `Member`, `Message` and the rest, with methods.
- `shoal.emojis`: the application's emojis, used across the bot by name.
- `shoal.client`: `Client`, which connects, caches and turns events into models.
- `shoal.ui`: views, buttons, selects and modals.
- `shoal.app_commands`: slash commands and context menus.
- `shoal.commands`: prefix and hybrid commands, `Bot`, cogs and extensions.
- `shoal.compat`: familiar names for bots moving over (`import shoal.compat as discord`).
"""

import importlib
from typing import TYPE_CHECKING, Final

from shoal._version import __version__

if TYPE_CHECKING:
    from shoal import app_commands, commands, ui
    from shoal.client import Client, Interaction
    from shoal.models import (
        Color,
        Colour,
        Embed,
        Emoji,
        Game,
        Guild,
        Member,
        Message,
        Object,
        Role,
        TextChannel,
        Thread,
        User,
    )
    from shoal.payloads import AllowedMentions, ButtonStyle, Intents, Permissions, StatusType
    from shoal.rest import File, VoiceMessage

_LAZY: Final[dict[str, str]] = {
    "AllowedMentions": "shoal.payloads",
    "ButtonStyle": "shoal.payloads",
    "Client": "shoal.client",
    "Color": "shoal.models",
    "Colour": "shoal.models",
    "Embed": "shoal.models",
    "Emoji": "shoal.models",
    "File": "shoal.rest",
    "Game": "shoal.models",
    "Guild": "shoal.models",
    "Intents": "shoal.payloads",
    "Interaction": "shoal.client",
    "Member": "shoal.models",
    "Message": "shoal.models",
    "Object": "shoal.models",
    "Permissions": "shoal.payloads",
    "Role": "shoal.models",
    "StatusType": "shoal.payloads",
    "TextChannel": "shoal.models",
    "Thread": "shoal.models",
    "User": "shoal.models",
    "VoiceMessage": "shoal.rest",
    "app_commands": "shoal.app_commands",
    "commands": "shoal.commands",
    "ui": "shoal.ui",
}
"""Where each top-level name lives; imported the first time it is used."""


def __getattr__(name: str) -> object:
    """Load a top-level name on first use (PEP 562)."""
    module = _LAZY.get(name)
    if module is None:
        msg = f"module 'shoal' has no attribute {name!r}"
        raise AttributeError(msg)
    loaded = importlib.import_module(module)
    value: object = loaded if module == f"shoal.{name}" else getattr(loaded, name)
    globals()[name] = value
    return value


__all__ = [
    "AllowedMentions",
    "ButtonStyle",
    "Client",
    "Color",
    "Colour",
    "Embed",
    "Emoji",
    "File",
    "Game",
    "Guild",
    "Intents",
    "Interaction",
    "Member",
    "Message",
    "Object",
    "Permissions",
    "Role",
    "StatusType",
    "TextChannel",
    "Thread",
    "User",
    "VoiceMessage",
    "__version__",
    "app_commands",
    "commands",
    "ui",
]
