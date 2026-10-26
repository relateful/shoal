"""Ready-made checks: permissions, roles and cooldowns.

    @tree.command()
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.cooldown(1, 10.0)
    async def purge(interaction: Interaction, count: int) -> None: ...

Discord: https://docs.discord.com/developers/interactions/application-commands#permissions
"""

from collections.abc import Callable, Hashable

from shoal.app_commands.commands import CooldownCheck, Decoratable, check
from shoal.app_commands.errors import (
    BotMissingPermissionsError,
    CommandOnCooldownError,
    MissingAnyRoleError,
    MissingPermissionsError,
    MissingRoleError,
    NoPrivateMessageError,
)
from shoal.client.interaction import Interaction
from shoal.core.clock import Clock
from shoal.core.cooldown import Cooldown
from shoal.models.member import Member
from shoal.payloads.permissions import Permissions

type CooldownKey = Callable[[Interaction], Hashable]
"""What a cooldown is counted per: the user, the guild, the channel, or anything else."""


def has_permissions[T: Decoratable](**permissions: bool) -> Callable[[T], T]:
    """Refuse users without these permissions in the channel, with `MissingPermissionsError`.

    Raises:
        TypeError: A name is not a permission.
    """
    wanted = Permissions(**permissions)

    def predicate(interaction: Interaction) -> bool:
        missing = list(wanted.without(interaction.permissions).enabled())
        if missing:
            raise MissingPermissionsError(missing)
        return True

    return check(predicate)


def bot_has_permissions[T: Decoratable](**permissions: bool) -> Callable[[T], T]:
    """Refuse when the bot lacks these permissions in the channel, with `BotMissingPermissionsError`.

    Raises:
        TypeError: A name is not a permission.
    """
    wanted = Permissions(**permissions)

    def predicate(interaction: Interaction) -> bool:
        missing = list(wanted.without(interaction.app_permissions).enabled())
        if missing:
            raise BotMissingPermissionsError(missing)
        return True

    return check(predicate)


def _member(interaction: Interaction) -> Member:
    user = interaction.user
    if not isinstance(user, Member):
        raise NoPrivateMessageError
    return user


def has_role[T: Decoratable](role: int | str) -> Callable[[T], T]:
    """Refuse users without `role` (an ID, or a name), with `MissingRoleError`."""

    def predicate(interaction: Interaction) -> bool:
        if not _member(interaction).has_role(role):
            raise MissingRoleError(role)
        return True

    return check(predicate)


def has_any_role[T: Decoratable](*roles: int | str) -> Callable[[T], T]:
    """Refuse users with none of `roles` (IDs or names), with `MissingAnyRoleError`."""

    def predicate(interaction: Interaction) -> bool:
        member = _member(interaction)
        if not any(member.has_role(role) for role in roles):
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


def cooldown[T: Decoratable](
    rate: int, per: float, *, key: CooldownKey = by_user, clock: Clock | None = None
) -> Callable[[T], T]:
    """Allow `rate` uses per `per` seconds per user (or per `key`); refuse with `CommandOnCooldownError`.

    `clock` measures the window (tests pass a fake one).

    Raises:
        ValueError: `rate` is below 1 or `per` is not positive.
    """
    limiter = Cooldown[Interaction](rate, per, key=key, clock=clock)

    def predicate(interaction: Interaction) -> bool:
        wait = limiter.update_rate_limit(interaction)
        if wait > 0:
            raise CommandOnCooldownError(wait)
        return True

    return check(CooldownCheck(predicate))
