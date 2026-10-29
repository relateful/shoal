"""`shoal.compat` against the public names of the library it eases moving from.

`discordpy_names.json` lists every name each of its packages exports. Each one is either in
`shoal.compat` or below, with why it is not; the test fails when a listed name appears (take it off
the list) and when a name is neither (add it to compat or explain it here).
"""

import importlib
from pathlib import Path
from types import ModuleType

import msgspec
import pytest

from shoal.core.codec import decode_json


class Snapshot(msgspec.Struct):
    source: str
    """The version the names were read from."""
    packages: dict[str, list[str]]


SNAPSHOT = decode_json((Path(__file__).parent / "discordpy_names.json").read_bytes(), Snapshot).packages

NO_COUNTERPART = "no Shoal counterpart yet"
PAYLOAD_INSTEAD = "Shoal gives the Discord payload for this; it has no model of this shape"
VOICE_SOURCES = "voice plays through AudioSource and FFmpegSource; this source or hook is not in Shoal"
WEBHOOK_MODEL = "webhooks are `rest.webhooks` calls and the `Webhook` payload, with no `send()` model yet"
CONTEXT_FLAGS = (
    "Shoal uses the `InteractionContextType` and `ApplicationIntegrationType` enums, not flag classes"
)

NOT_PROVIDED: dict[str, dict[str, str]] = {
    "discord": {
        "AppCommandContext": CONTEXT_FLAGS,
        "AppInstallationType": CONTEXT_FLAGS,
        "AuditLogActionCategory": NO_COUNTERPART,
        "AuditLogChanges": "audit log changes are `AuditLogChange` payloads with raw old and new values",
        "AuditLogDiff": "audit log changes are `AuditLogChange` payloads with raw old and new values",
        "AutoModPresets": "keyword presets are the `AutoModerationKeywordPresetType` enum, not a flag class",
        "BaseActivity": "activities are the `Activity` payload",
        "BotIntegration": "integrations are the `Integration` payload",
        "Collectible": "collectibles are the `Collectibles` and `Nameplate` payloads",
        "CollectibleType": NO_COUNTERPART,
        "Color": "embed colours are integers; there is no colour class yet",
        "Colour": "embed colours are integers; there is no colour class yet",
        "DefaultAvatar": NO_COUNTERPART,
        "DeletedReferencedMessage": NO_COUNTERPART,
        "Enum": "an enum base class; Shoal's open enums live in `shoal.core`",
        "FFmpegAudio": VOICE_SOURCES,
        "FFmpegOpusAudio": VOICE_SOURCES,
        "FFmpegProcessError": VOICE_SOURCES,
        "GatewayNotFound": NO_COUNTERPART,
        "GuildProductPurchase": NO_COUNTERPART,
        "InteractionCallbackActivityInstance": NO_COUNTERPART,
        "MediaItemLoadingState": NO_COUNTERPART,
        "MemberCacheFlags": "the cache is configured with `CachePolicy`, per kind of object",
        "MessageApplication": PAYLOAD_INSTEAD,
        "NameplatePalette": NO_COUNTERPART,
        "PCMAudio": VOICE_SOURCES,
        "PCMVolumeTransformer": VOICE_SOURCES,
        "PartialIntegration": PAYLOAD_INSTEAD,
        "PartialInviteChannel": PAYLOAD_INSTEAD,
        "PermissionOverwrite": "`Overwrite` is Discord's allow and deny payload, not a per-flag builder",
        "PurchaseNotification": NO_COUNTERPART,
        "RawReactionActionEvent": "`MessageReactionAdd` and `MessageReactionRemove` are separate payloads",
        "RawThreadDeleteEvent": NO_COUNTERPART,
        "RawThreadUpdateEvent": NO_COUNTERPART,
        "SelectMenu": "received selects are typed by kind: `StringSelect`, `UserSelect` and the rest",
        "ShardInfo": "shards are `shoal.gateway.Shard`",
        "Spotify": "activities are the `Activity` payload",
        "StandardSticker": "stickers are the `Sticker` payload, whatever their type",
        "StreamIntegration": "integrations are the `Integration` payload",
        "SyncWebhook": WEBHOOK_MODEL,
        "SyncWebhookMessage": WEBHOOK_MODEL,
        "VoiceChannelSoundEffect": NO_COUNTERPART,
        "VoiceProtocol": VOICE_SOURCES,
        "Webhook": WEBHOOK_MODEL,
        "WebhookMessage": WEBHOOK_MODEL,
    },
    "discord.ext.commands": {
        "CogMeta": "a metaclass; Shoal's `Cog` needs none",
        "CooldownMapping": "Shoal's `Cooldown` keys uses itself; there is no separate mapping",
        "DynamicCooldownMapping": "Shoal's `DynamicCooldown` keys uses itself; there is no separate mapping",
        "GroupMixin": "a shared base class; Shoal's `Bot` and `Group` do not have one",
        "IDConverter": "a shared base class; Shoal's converters do not have one",
    },
    "discord.app_commands": {
        "AllChannels": NO_COUNTERPART,
        "AppCommandChannel": NO_COUNTERPART,
        "AppCommandContext": CONTEXT_FLAGS,
        "AppCommandGroup": NO_COUNTERPART,
        "AppCommandPermissions": "permissions are the `ApplicationCommandPermission` payload",
        "AppCommandThread": NO_COUNTERPART,
        "AppInstallationType": CONTEXT_FLAGS,
        "Argument": NO_COUNTERPART,
        "GuildAppCommandPermissions": "permissions are the `GuildApplicationCommandPermissions` payload",
        "Timestamp": NO_COUNTERPART,
        "TranslationContextTypes": NO_COUNTERPART,
    },
    "discord.ui": {"DynamicItem": "no persistent dynamic items in `shoal.ui` yet"},
    "discord.ext.tasks": {},
    "discord.utils": {"setup_logging": NO_COUNTERPART, "sleep_until": NO_COUNTERPART},
}

COMPAT = {
    "discord": "shoal.compat",
    "discord.ext.commands": "shoal.compat.commands",
    "discord.app_commands": "shoal.compat.app_commands",
    "discord.ui": "shoal.ui",
    "discord.ext.tasks": "shoal.tasks",
    "discord.utils": "shoal.compat.utils",
}


def compat_module(package: str) -> ModuleType:
    return importlib.import_module(COMPAT[package])


@pytest.mark.parametrize("package", sorted(COMPAT))
def test_every_discord_py_name_is_in_compat_or_explained(package: str) -> None:
    module = compat_module(package)
    names = set(SNAPSHOT[package])
    explained = NOT_PROVIDED[package]
    assert set(explained) <= names, "explained names must be in the snapshot"
    missing = sorted(name for name in names - set(explained) if not hasattr(module, name))
    assert missing == [], f"{package}: add these to {COMPAT[package]} or explain them in NOT_PROVIDED"
    now_provided = sorted(name for name in explained if hasattr(module, name))
    assert now_provided == [], f"{package}: these are provided now; take them off NOT_PROVIDED"


def test_compat_covers_most_of_discord_py() -> None:
    total = sum(len(SNAPSHOT[package]) for package in COMPAT)
    unexplained = sum(len(NOT_PROVIDED[package]) for package in COMPAT)
    assert (total - unexplained) / total > 0.85
