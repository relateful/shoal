"""The application's own emojis: a registry by name, and a sync from a folder of images.

    await client.app_emojis.sync(Path("assets/emojis"))
    await channel.send(f"{client.app_emojis['approve']} Saved")

From a shell: `python -m shoal.emojis sync assets/emojis --dry-run`.

Discord: https://docs.discord.com/developers/resources/emoji#emoji-object-applicationowned-emoji
"""

from shoal.emojis.registry import AppEmojis, DeclaredEmoji, EmojisNotLoadedError, app_emoji
from shoal.emojis.sync import (
    LocalEmoji,
    Manifest,
    ManifestEntry,
    SyncReport,
    find_emojis,
    read_manifest,
    sync_emojis,
)

__all__ = [
    "AppEmojis",
    "DeclaredEmoji",
    "EmojisNotLoadedError",
    "LocalEmoji",
    "Manifest",
    "ManifestEntry",
    "SyncReport",
    "app_emoji",
    "find_emojis",
    "read_manifest",
    "sync_emojis",
]
