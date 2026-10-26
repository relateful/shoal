"""Defaults for the application emoji registry and sync."""

from typing import Final

IMAGE_SUFFIXES: Final = frozenset({".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"})
"""The files a sync uploads: the formats Discord takes for emojis."""

MANIFEST_NAME: Final = "emojis.lock.json"
"""The manifest a sync keeps in the emoji folder: each emoji's ID and image fingerprint, per
application. Commit it with the images so any machine can sync without re-uploading."""

SYNC_ROUNDS: Final = 3
"""How many times a sync tries an emoji that keeps failing for a temporary reason (a server error or
a dropped connection) before reporting it."""

SYNC_ROUND_PAUSE: Final = 5.0
"""Seconds before a sync retries what failed for a temporary reason, multiplied by the round."""
