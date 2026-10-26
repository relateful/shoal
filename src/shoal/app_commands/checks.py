"""Ready-made checks: permissions, roles and cooldowns.

    @tree.command()
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.cooldown(1, 10.0)
    async def purge(interaction: Interaction, count: int) -> None: ...

Discord: https://docs.discord.com/developers/interactions/application-commands#permissions
"""

import time
from collections.abc import Callable, Hashable
from typing import Final

from shoal.app_commands.commands import Decoratable, check
from shoal.app_commands.errors import (
    BotMissingPermissionsError,
    CommandOnCooldownError,
    MissingAnyRoleError,
    MissingPermissionsError,
    MissingRoleError,
    NoPrivateMessageError,
)
from shoal.client.interaction import Interaction
from shoal.models.member import Member
from shoal.payloads.permissions import Permissions

type CooldownKey = Callable[[Interaction], Hashable]
"""What a cooldown is counted per: the user, the guild, the channel, or anything else."""


def _missing(have: Permissions, wanted: dict[str, bool]) -> list[str]:
    return [name for name, value in wanted.items() if value and not getattr(have, name)]


def _known(permissions: dict[str, bool]) -> dict[str, bool]:
    Permissions(**permissions)  # Raises TypeError for a name that is not a permission.
    return permissions


def has_permissions[T: Decoratable](**permissions: bool) -> Callable[[T], T]:
    """Refuse users without these permissions in the channel, with `MissingPermissionsError`.

    Raises:
        TypeError: A name is not a permission.
    """
    wanted = _known(permissions)

    def predicate(interaction: Interaction) -> bool:
        missing = _missing(interaction.permissions, wanted)
        if missing:
            raise MissingPermissionsError(missing)
        return True

    return check(predicate)


def bot_has_permissions[T: Decoratable](**permissions: bool) -> Callable[[T], T]:
    """Refuse when the bot lacks these permissions in the channel, with `BotMissingPermissionsError`.

    Raises:
        TypeError: A name is not a permission.
    """
    wanted = _known(permissions)

    def predicate(interaction: Interaction) -> bool:
        missing = _missing(interaction.app_permissions, wanted)
        if missing:
            raise BotMissingPermissionsError(missing)
        return True

    return check(predicate)


def _member(interaction: Interaction) -> Member:
    user = interaction.user
    if not isinstance(user, Member):
        raise NoPrivateMessageError
    return user


def _has_role(member: Member, role: int | str) -> bool:
    if isinstance(role, int):
        return role in member.raw_roles
    return any(found.name == role for found in member.roles)


def has_role[T: Decoratable](role: int | str) -> Callable[[T], T]:
    """Refuse users without `role` (an ID, or a name), with `MissingRoleError`."""

    def predicate(interaction: Interaction) -> bool:
        if not _has_role(_member(interaction), role):
            raise MissingRoleError(role)
        return True

    return check(predicate)


def has_any_role[T: Decoratable](*roles: int | str) -> Callable[[T], T]:
    """Refuse users with none of `roles` (IDs or names), with `MissingAnyRoleError`."""

    def predicate(interaction: Interaction) -> bool:
        member = _member(interaction)
        if not any(_has_role(member, role) for role in roles):
            raise MissingAnyRoleError(roles)
        return True

    return check(predicate)


def by_user(interaction: Interaction) -> Hashable:
    """Count a cooldown per user (the default)."""
    return interaction.user.id


def by_guild(interaction: Interaction) -> Hashable:
    """Count a cooldown per guild; in DMs, per user."""
    return interaction.guild_id if interaction.guild_id is not None else interaction.user.id


def by_channel(interaction: Interaction) -> Hashable:
    """Count a cooldown per channel."""
    return interaction.channel_id


_FORGET_AFTER: Final = 1024
"""How many keys a cooldown holds before it drops the ones whose window has passed."""


class Cooldown:
    """`rate` uses per `per` seconds for each key, as a sliding window.

    State lives in this process: with several processes, each counts on its own.
    """

    __slots__ = ("_clock", "_uses", "key", "per", "rate")

    def __init__(
        self,
        rate: int,
        per: float,
        *,
        key: CooldownKey = by_user,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """A cooldown allowing `rate` uses per `per` seconds.

        Raises:
            ValueError: `rate` is below 1 or `per` is not positive.
        """
        if rate < 1 or per <= 0:
            msg = f"a cooldown needs rate >= 1 and per > 0, not {rate} per {per}"
            raise ValueError(msg)
        self.rate: int = rate
        self.per: float = per
        self.key: CooldownKey = key
        self._clock: Callable[[], float] = clock
        self._uses: dict[Hashable, list[float]] = {}

    @property
    def tracked(self) -> int:
        """How many keys the cooldown is holding uses for."""
        return len(self._uses)

    def retry_after(self, interaction: Interaction) -> float:
        """Record a use; return 0.0 when allowed, or how many seconds until the next one is."""
        now = self._clock()
        if len(self._uses) >= _FORGET_AFTER:
            self._uses = {key: uses for key, uses in self._uses.items() if uses and uses[-1] > now - self.per}
        key = self.key(interaction)
        uses = [moment for moment in self._uses.get(key, []) if moment > now - self.per]
        if len(uses) >= self.rate:
            self._uses[key] = uses
            return uses[0] + self.per - now
        uses.append(now)
        self._uses[key] = uses
        return 0.0


def cooldown[T: Decoratable](rate: int, per: float, *, key: CooldownKey = by_user) -> Callable[[T], T]:
    """Allow `rate` uses per `per` seconds per user (or per `key`); refuse with `CommandOnCooldownError`.

    Raises:
        ValueError: `rate` is below 1 or `per` is not positive.
    """
    limiter = Cooldown(rate, per, key=key)

    def predicate(interaction: Interaction) -> bool:
        wait = limiter.retry_after(interaction)
        if wait > 0:
            raise CommandOnCooldownError(wait)
        return True

    return check(predicate)
