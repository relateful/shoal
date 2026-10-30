"""A permission overwrite built one permission at a time, as allowed, denied or left alone.

    overwrite = PermissionOverwrite(view_channel=False, send_messages=True)
    await channel.set_permissions(guild.default_role, overwrite=overwrite)
    await guild.create_text_channel("staff", overwrites={guild.default_role: overwrite})

Discord stores an overwrite as two bit sets, `allow` and `deny`; `pair()` and `from_pair()` convert.

Discord: https://docs.discord.com/developers/resources/channel#overwrite-object
"""

from collections.abc import Iterator, Mapping, Sequence
from typing import Final, Self, override

from shoal.core.snowflake import Snowflake
from shoal.models.base import Hashable
from shoal.payloads.channel import Overwrite, OverwriteType, PartialOverwrite
from shoal.payloads.permissions import Permissions

ALIASES: Final[dict[str, str]] = {
    "read_messages": "view_channel",
    "manage_permissions": "manage_roles",
    "use_slash_commands": "use_application_commands",
    "external_emojis": "use_external_emojis",
    "external_stickers": "use_external_stickers",
    "manage_emojis": "manage_guild_expressions",
    "manage_emojis_and_stickers": "manage_guild_expressions",
    "manage_expressions": "manage_guild_expressions",
    "create_expressions": "create_guild_expressions",
    "start_embedded_activities": "use_embedded_activities",
    "use_voice_activation": "use_vad",
}
"""Older and shorter names for permissions, accepted wherever a permission is named here."""


def _name(name: str) -> str:
    """The permission's Discord name.

    Raises:
        AttributeError: `name` is not a permission.
    """
    name = ALIASES.get(name, name)
    if name not in Permissions.known_flags:
        msg = f"{name!r} is not a permission"
        raise AttributeError(msg)
    return name


class PermissionOverwrite:
    """Each permission allowed (`True`), denied (`False`) or left to the role or guild (`None`).

    Permissions read and set as attributes: `overwrite.send_messages = False`. Unset ones are
    `None`. Two overwrites are equal when they allow and deny the same permissions.
    """

    __slots__ = ("_values",)

    def __init__(self, **permissions: bool | None) -> None:
        """Allow, deny or leave alone each permission named.

        Raises:
            AttributeError: A keyword is not a permission.
        """
        self._values: dict[str, bool] = {}
        self.update(**permissions)

    @classmethod
    def from_pair(cls, allow: Permissions, deny: Permissions) -> Self:
        """An overwrite from its allowed and denied bit sets; a bit in both is denied."""
        overwrite = cls()
        for name in allow.enabled():
            overwrite._values[name] = True
        for name in deny.enabled():
            overwrite._values[name] = False
        return overwrite

    @classmethod
    def from_overwrite(cls, overwrite: Overwrite | PartialOverwrite) -> Self:
        """The overwrite a channel has, as read from `channel.overwrites`."""
        allow = overwrite.allow if isinstance(overwrite.allow, Permissions) else Permissions.none()
        deny = overwrite.deny if isinstance(overwrite.deny, Permissions) else Permissions.none()
        return cls.from_pair(allow, deny)

    def pair(self) -> tuple[Permissions, Permissions]:
        """The allowed and the denied permissions."""
        allow = Permissions(**{name: True for name, value in self._values.items() if value})
        deny = Permissions(**{name: True for name, value in self._values.items() if not value})
        return allow, deny

    def to_payload(self, target_id: int, kind: OverwriteType) -> PartialOverwrite:
        """The overwrite for a role or member, as a request takes it."""
        allow, deny = self.pair()
        return PartialOverwrite(id=Snowflake(target_id), type=kind, allow=allow, deny=deny)

    def is_empty(self) -> bool:
        """Whether every permission is left alone."""
        return not self._values

    def update(self, **permissions: bool | None) -> None:
        """Allow, deny or (with `None`) leave alone each permission named.

        Raises:
            AttributeError: A keyword is not a permission.
        """
        names = {_name(name): value for name, value in permissions.items()}
        for name, value in names.items():
            if value is None:
                self._values.pop(name, None)
            else:
                self._values[name] = value

    def __getattr__(self, name: str) -> bool | None:
        return self._values.get(_name(name))

    @override
    def __setattr__(self, name: str, value: object) -> None:
        if name == "_values":
            object.__setattr__(self, name, value)
            return
        if value is not None and not isinstance(value, bool):
            msg = f"a permission is True, False or None, not {value!r}"
            raise TypeError(msg)
        self.update(**{name: value})

    def __iter__(self) -> Iterator[tuple[str, bool | None]]:
        """Every permission and its value, in bit order."""
        for name, _ in sorted(Permissions.known_flags.items(), key=lambda item: item[1]):
            yield name, self._values.get(name)

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PermissionOverwrite):
            return NotImplemented
        return self._values == other._values

    __hash__ = None  # type: ignore[assignment]  # mutable

    @override
    def __repr__(self) -> str:
        values = ", ".join(f"{name}={value}" for name, value in sorted(self._values.items()))
        return f"PermissionOverwrite({values})"


type OverwritesLike = Mapping[Hashable, PermissionOverwrite] | Sequence[PartialOverwrite]
"""Overwrites for a new channel: a `PermissionOverwrite` per role or member, or the payloads."""


def overwrite_payloads(overwrites: OverwritesLike) -> list[PartialOverwrite]:
    """The overwrites as a request takes them; a role's is a role overwrite, anything else a member's."""
    from shoal.models.role import Role

    if not isinstance(overwrites, Mapping):
        return list(overwrites)
    return [
        overwrite.to_payload(
            target.id, OverwriteType.ROLE if isinstance(target, Role) else OverwriteType.MEMBER
        )
        for target, overwrite in overwrites.items()
    ]
