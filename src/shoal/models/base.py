"""What every model with an ID shares: equality, hashing and creation time by ID.

Discord: https://docs.discord.com/developers/reference#snowflakes
"""

from datetime import datetime
from typing import Final, override

from shoal.core.snowflake import Snowflake


class Hashable:
    """Compares and hashes by type and `id`.

    Two `Member` objects for the same user in the same guild are equal even when built from
    different cache reads.
    """

    __slots__ = ()

    @property
    def id(self) -> Snowflake:
        """The object's ID."""
        raise NotImplementedError

    @property
    def created_at(self) -> datetime:
        """When the object was created, read from its ID."""
        return self.id.created_at

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Hashable) and type(other) is type(self) and other.id == self.id

    @override
    def __hash__(self) -> int:
        return hash((type(self).__name__, int(self.id)))


class Object(Hashable):
    """Anything with an ID, when only the ID is known.

    Pass one wherever a method takes a role, member, channel or guild and you have only the ID.
    """

    __slots__ = ("_id",)

    def __init__(self, id: int) -> None:  # noqa: A002 - `Object(id=...)` reads as the ID it holds
        """An object with only an ID."""
        self._id: Snowflake = Snowflake(id)

    @property
    @override
    def id(self) -> Snowflake:
        return self._id

    @override
    def __repr__(self) -> str:
        return f"<Object id={int(self._id)}>"


class MissingType:
    """The type of `MISSING`: an `edit(...)` keyword that was left out. `None` means clear it."""

    __slots__ = ()


MISSING: Final = MissingType()
"""The default of every `edit(...)` keyword: leave that part as it is."""
