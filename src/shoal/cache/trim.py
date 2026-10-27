"""Per-field trimming: cache only the fields a bot reads.

    CacheConfig(policies={EntityKind.CHANNEL: CachePolicy(fields=frozenset({"name", "topic"}))})

Every other field is reset to its default (`None`, `UNSET`, an empty list) before the value is
stored, so memory, Redis and snapshots hold only what was asked for. Fields Discord always sends
(no default) and the fields that tie objects together (`_ALWAYS_KEPT`) are never trimmed.
"""

from collections.abc import Callable, Iterable
from typing import Final, final

import msgspec

from shoal.cache.policy import EntityKind

_ALWAYS_KEPT: Final = frozenset({"channel_id", "guild_id", "id", "type", "user", "user_id"})
"""Fields that say what an object is and where it belongs; models and the cache rely on them."""


@final
class FieldTrim:
    """Resets the fields of one kind's values that its policy does not keep.

    Args:
        kind: The entity kind, for error messages.
        value_type: The struct the kind is cached as.
        fields: The fields to keep, besides those always kept.

    Raises:
        ValueError: A field is not one of the struct's.
    """

    __slots__ = ("_resets",)

    def __init__(self, kind: EntityKind, value_type: type[msgspec.Struct], fields: Iterable[str]) -> None:
        """Work out which fields to reset; see the class docstring for the arguments."""
        info = msgspec.structs.fields(value_type)
        known = {field.name for field in info}
        kept = frozenset(fields)
        if unknown := sorted(kept - known):
            msg = f"{kind} is cached as {value_type.__name__}, which has no field {', '.join(unknown)}"
            raise ValueError(msg)
        self._resets: tuple[tuple[str, Callable[[], object]], ...] = tuple(
            (field.name, _default(field))
            for field in info
            if field.name not in kept and field.name not in _ALWAYS_KEPT and _has_default(field)
        )

    def __call__[V](self, value: V) -> V:
        """`value` with the fields not kept reset to their defaults."""
        if not self._resets or not isinstance(value, msgspec.Struct):
            return value
        return msgspec.structs.replace(value, **{name: default() for name, default in self._resets})


def _has_default(field: msgspec.structs.FieldInfo) -> bool:
    return field.default is not msgspec.NODEFAULT or field.default_factory is not msgspec.NODEFAULT


def _default(field: msgspec.structs.FieldInfo) -> Callable[[], object]:
    if field.default_factory is not msgspec.NODEFAULT:
        factory: Callable[[], object] = field.default_factory
        return factory
    value: object = field.default
    return lambda: value
