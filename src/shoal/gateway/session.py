"""Gateway sessions that survive a restart.

Discord replays missed events to a client that resumes a session, and resuming spends no session start
from the daily limit. A shard that saves its session on shutdown and loads it on start can therefore
pick up where it left off after a deploy, instead of identifying again and receiving every guild anew.

Whether a session is still resumable is decided by Discord: a stale one is answered with Invalid
Session, after which the shard identifies normally. `max_age` only avoids attempts that are certain
to fail.

Discord: https://docs.discord.com/developers/events/gateway#resuming
"""

import asyncio
import logging
from pathlib import Path
from typing import Protocol, final, override

import msgspec

from shoal.core.clock import Clock, SystemClock
from shoal.core.codec import PayloadDecodeError, decode_json, encode_json
from shoal.core.files import write_private
from shoal.gateway.defaults import RESUME_WINDOW

_log = logging.getLogger("shoal.gateway")


class GatewaySession(msgspec.Struct, frozen=True, kw_only=True):
    """What a shard needs to resume: the values from Ready plus the last sequence number.

    Discord: https://docs.discord.com/developers/events/gateway#preparing-to-resume
    """

    shard_id: int
    shard_count: int
    session_id: str
    sequence: int
    resume_gateway_url: str
    saved_at: float
    """Unix time the session was saved."""


class SessionStore(Protocol):
    """Persists sessions between process restarts."""

    __slots__ = ()

    async def load(self, shard_id: int, shard_count: int) -> GatewaySession | None:
        """Return the saved session for this shard layout, or `None`."""
        ...

    async def save(self, session: GatewaySession) -> None:
        """Store a session, replacing any previous one for the shard."""
        ...

    async def delete(self, shard_id: int) -> None:
        """Forget the session for a shard (it was invalidated)."""
        ...


@final
class MemorySessionStore(SessionStore):
    """Keeps sessions in memory: survives reconnects, not process restarts. Useful in tests."""

    __slots__ = ("_sessions",)

    def __init__(self) -> None:
        """Create an empty store."""
        self._sessions: dict[int, GatewaySession] = {}

    @override
    async def load(self, shard_id: int, shard_count: int) -> GatewaySession | None:
        session = self._sessions.get(shard_id)
        if session is None or session.shard_count != shard_count:
            return None
        return session

    @override
    async def save(self, session: GatewaySession) -> None:
        self._sessions[session.shard_id] = session

    @override
    async def delete(self, shard_id: int) -> None:
        self._sessions.pop(shard_id, None)


@final
class FileSessionStore(SessionStore):
    """One JSON file per shard in a directory, written atomically.

    Args:
        directory: Where `shard-<id>.json` files live. Created if missing.
        max_age: Seconds after which a saved session is not worth trying. Shoal's heuristic, not a
            documented Discord limit.
        clock: Time source.

    A session file holds the session id, which with the bot token can resume the session. Files are
    created readable by the bot's user only on POSIX systems; on Windows they take the directory's
    access rules, so give the store a directory only the bot's user can read. Writes are atomic.
    """

    __slots__ = ("_clock", "_directory", "_max_age")

    def __init__(
        self, directory: str | Path, *, max_age: float = RESUME_WINDOW, clock: Clock | None = None
    ) -> None:
        """Create a store; see the class docstring for the arguments."""
        self._directory: Path = Path(directory)
        self._max_age: float = max_age
        self._clock: Clock = clock or SystemClock()

    def _path(self, shard_id: int) -> Path:
        return self._directory / f"shard-{shard_id}.json"

    @override
    async def load(self, shard_id: int, shard_count: int) -> GatewaySession | None:
        path = self._path(shard_id)
        try:
            data = await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError:
            return None
        except OSError:
            _log.exception("session file %s cannot be read; identifying a new session", path)
            return None
        try:
            session = decode_json(data, GatewaySession)
        except PayloadDecodeError:
            _log.warning("session file %s is corrupt; deleting it and identifying a new session", path)
            await self._discard(shard_id)
            return None
        age = self._clock.wall() - session.saved_at
        # A negative age means the clock moved backwards; the file cannot be dated, so it is not trusted.
        if session.shard_count != shard_count or not 0 <= age <= self._max_age:
            await self._discard(shard_id)
            return None
        return session

    @override
    async def save(self, session: GatewaySession) -> None:
        await asyncio.to_thread(write_private, self._path(session.shard_id), encode_json(session))

    @override
    async def delete(self, shard_id: int) -> None:
        await asyncio.to_thread(self._path(shard_id).unlink, missing_ok=True)

    async def _discard(self, shard_id: int) -> None:
        """Delete a file `load` cannot use; failing to only means trying again on the next start."""
        try:
            await self.delete(shard_id)
        except OSError:
            _log.exception("session file for shard %d could not be deleted", shard_id)
