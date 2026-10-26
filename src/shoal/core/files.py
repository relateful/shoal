"""Writing files that hold private state (sessions, cache snapshots).

Both kinds of file contain data that belongs to the bot and its users, so they are written readable by
the bot's own user only, and atomically: a crash mid-write leaves the previous file intact.
"""

import os
import tempfile
from pathlib import Path
from typing import Final

_PRIVATE_DIRECTORY_MODE: Final = 0o700
"""Owner-only directories. Ignored on Windows, where files inherit the directory's ACL."""


def write_private(path: Path, data: bytes) -> None:
    """Replace `path` with `data` atomically, creating it (and its directory) owner-only.

    Owner-only applies on POSIX systems. Windows ignores the mode: the file takes the directory's
    access rules, so keep it in a directory only the bot's user can read.

    Blocks; call it through `asyncio.to_thread`.
    """
    path.parent.mkdir(mode=_PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)
    # mkstemp creates the file with mode 0o600 and a unique name, so concurrent writers never share
    # a temporary file.
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        try:
            file = os.fdopen(descriptor, "wb")
        except BaseException:
            os.close(descriptor)
            raise
        with file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    _sync_directory(path.parent)


def _sync_directory(directory: Path) -> None:
    """Make the rename itself durable on POSIX. Windows refuses to open a directory, and does not need to.

    Blocks; call it through `asyncio.to_thread`.
    """
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except PermissionError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
