"""Sync the application's emojis with a folder of images from the command line.

    DISCORD_TOKEN=... python -m shoal.emojis sync assets/emojis --dry-run

The bot token is read from an environment variable (`--token-env`, `DISCORD_TOKEN` by default), never
from the command line, where it would land in the shell's history. Exits 1 when an emoji failed.

Discord: https://docs.discord.com/developers/resources/emoji#create-application-emoji
"""

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from shoal.emojis.sync import SyncReport, sync_emojis
from shoal.rest.client import RestClient, Token


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the command; returns the exit status."""
    parser = argparse.ArgumentParser(
        prog="python -m shoal.emojis", description="Sync the application's emojis with a folder of images."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync", help="make the application's emojis match a folder of images")
    sync.add_argument("folder", type=Path, help="the images; each file's name is its emoji's name")
    sync.add_argument("--manifest", type=Path, help="where the manifest lives (default: in the folder)")
    sync.add_argument("--prune", action="store_true", help="delete emojis that have no image")
    sync.add_argument(
        "--replace-unknown", action="store_true", help="replace emojis the manifest does not know"
    )
    sync.add_argument("--dry-run", action="store_true", help="only report what would change")
    sync.add_argument("--token-env", default="DISCORD_TOKEN", help="the variable holding the bot token")
    options = parser.parse_args(arguments)
    token = os.environ.get(options.token_env)
    if not token:
        parser.error(f"set {options.token_env} to the bot's token")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = asyncio.run(
        _sync(
            token,
            options.folder,
            manifest=options.manifest,
            prune=options.prune,
            replace_unknown=options.replace_unknown,
            dry_run=options.dry_run,
        )
    )
    sys.stdout.write(f"{report}\n")
    return 0 if report.ok else 1


async def _sync(
    token: str, folder: Path, *, manifest: Path | None, prune: bool, replace_unknown: bool, dry_run: bool
) -> SyncReport:
    async with RestClient(Token.bot(token)) as rest:
        application = await rest.applications.get_me()
        return await sync_emojis(
            rest,
            application.id,
            folder,
            manifest=manifest,
            prune=prune,
            replace_unknown=replace_unknown,
            dry_run=dry_run,
        )


if __name__ == "__main__":
    sys.exit(main())
