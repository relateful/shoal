"""Checks for prefix and hybrid commands: permissions, roles, owner, place, cooldowns.

    @bot.command()
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 10.0, commands.BucketType.USER)
    async def purge(ctx: commands.Context, count: int) -> None: ...

Each decorator works above or below `@command`. A check raises a `CheckFailureError` subclass that
says what was missing, which `Bot.on_command_error` (or the command's own handler) receives.
"""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Final

from shoal.commands.core import BucketType, Check, Command, Hook, MaxConcurrency, PendingSettings, pending_of
from shoal.commands.errors import (
    BotMissingAnyRoleError,
    BotMissingPermissionsError,
    BotMissingRoleError,
    CheckAnyFailureError,
    CheckFailureError,
    MissingAnyRoleError,
    MissingPermissionsError,
    MissingRoleError,
    NoPrivateMessageError,
    NotOwnerError,
    NSFWChannelRequiredError,
    PrivateMessageOnlyError,
)
from shoal.core.clock import Clock
from shoal.core.cooldown import Cooldown, DynamicCooldown
from shoal.models.channel import GuildChannel
from shoal.models.member import Member
from shoal.models.thread import Thread
from shoal.payloads.permissions import Permissions

if TYPE_CHECKING:
    from shoal.commands.context import Context

type Decoratable = Callable[..., Awaitable[None]] | Command

DM_PERMISSIONS: Final = Permissions(
    view_channel=True,
    send_messages=True,
    send_tts_messages=True,
    embed_links=True,
    attach_files=True,
    read_message_history=True,
    add_reactions=True,
    use_external_emojis=True,
    use_external_stickers=True,
)
"""What anyone can do in a DM, for permission checks outside guilds."""


class CheckDecorator:
    """What `check` returns: a decorator that adds `predicate`, which `check_any` can combine."""

    __slots__ = ("predicate",)

    def __init__(self, predicate: Check) -> None:
        """A decorator adding `predicate`."""
        self.predicate: Check = predicate

    def __call__[T: Decoratable](self, target: T) -> T:
        """Add the check to a command, or to a function that becomes one."""
        predicate = self.predicate
        return _apply(
            target,
            lambda command: command.add_check(predicate),
            lambda pending: pending.checks.append(predicate),
        )


def _apply[T: Decoratable](
    target: T, on_command: Callable[[Command], object], on_function: Callable[[PendingSettings], object]
) -> T:
    """Apply a setting to a command, or record it on a function that becomes one."""
    match target:
        case Command():
            on_command(target)
        case _:
            on_function(pending_of(target))
    return target


def check(predicate: Check) -> CheckDecorator:
    """Run `predicate` before the command; `False` refuses with `CheckFailureError`."""
    return CheckDecorator(predicate)


def check_any(*checks: CheckDecorator) -> CheckDecorator:
    """Allow the command when any of `checks` passes; `CheckAnyFailureError` when none does."""

    async def predicate(ctx: "Context") -> bool:
        errors: list[CheckFailureError] = []
        for each in checks:
            try:
                result = each.predicate(ctx)
                if await result if isinstance(result, Awaitable) else result:
                    return True
            except CheckFailureError as error:
                errors.append(error)
        raise CheckAnyFailureError(errors)

    return check(predicate)


def channel_permissions(ctx: "Context", member: Member | None) -> Permissions:
    """What `member` may do in the context's channel; DM permissions outside guilds."""
    channel = ctx.channel
    if member is None or not isinstance(channel, GuildChannel | Thread):
        return DM_PERMISSIONS
    return channel.permissions_for(member)


def has_permissions(**permissions: bool) -> CheckDecorator:
    """Refuse authors without these permissions in the channel, with `MissingPermissionsError`.

    Raises:
        TypeError: A name is not a permission.
    """
    wanted = Permissions(**permissions)

    def predicate(ctx: "Context") -> bool:
        if ctx.interaction is not None and ctx.guild is not None:
            have = ctx.interaction.permissions
        else:
            have = channel_permissions(ctx, ctx.author if isinstance(ctx.author, Member) else None)
        missing = list(wanted.without(have).enabled())
        if missing:
            raise MissingPermissionsError(missing)
        return True

    return check(predicate)


def bot_has_permissions(**permissions: bool) -> CheckDecorator:
    """Refuse when the bot lacks these permissions in the channel, with `BotMissingPermissionsError`.

    Raises:
        TypeError: A name is not a permission.
    """
    wanted = Permissions(**permissions)

    def predicate(ctx: "Context") -> bool:
        if ctx.interaction is not None:
            have = ctx.interaction.app_permissions
        else:
            me = ctx.me
            have = channel_permissions(ctx, me if isinstance(me, Member) else None)
        missing = list(wanted.without(have).enabled())
        if missing:
            raise BotMissingPermissionsError(missing)
        return True

    return check(predicate)


def has_guild_permissions(**permissions: bool) -> CheckDecorator:
    """Refuse authors without these permissions across the guild, with `MissingPermissionsError`.

    Raises:
        TypeError: A name is not a permission.
    """
    wanted = Permissions(**permissions)

    def predicate(ctx: "Context") -> bool:
        missing = list(wanted.without(_member(ctx.author).guild_permissions).enabled())
        if missing:
            raise MissingPermissionsError(missing)
        return True

    return check(predicate)


def bot_has_guild_permissions(**permissions: bool) -> CheckDecorator:
    """Refuse when the bot lacks these permissions across the guild, with `BotMissingPermissionsError`.

    Raises:
        TypeError: A name is not a permission.
    """
    wanted = Permissions(**permissions)

    def predicate(ctx: "Context") -> bool:
        missing = list(wanted.without(_member(ctx.me).guild_permissions).enabled())
        if missing:
            raise BotMissingPermissionsError(missing)
        return True

    return check(predicate)


def _member(user: object) -> Member:
    if not isinstance(user, Member):
        raise NoPrivateMessageError
    return user


def has_role(role: int | str) -> CheckDecorator:
    """Refuse authors without `role` (an ID, or a name), with `MissingRoleError`."""

    def predicate(ctx: "Context") -> bool:
        if not _member(ctx.author).has_role(role):
            raise MissingRoleError(role)
        return True

    return check(predicate)


def has_any_role(*roles: int | str) -> CheckDecorator:
    """Refuse authors with none of `roles` (IDs or names), with `MissingAnyRoleError`."""

    def predicate(ctx: "Context") -> bool:
        member = _member(ctx.author)
        if not any(member.has_role(role) for role in roles):
            raise MissingAnyRoleError(roles)
        return True

    return check(predicate)


def bot_has_role(role: int | str) -> CheckDecorator:
    """Refuse when the bot lacks `role` (an ID, or a name), with `BotMissingRoleError`."""

    def predicate(ctx: "Context") -> bool:
        if not _member(ctx.me).has_role(role):
            raise BotMissingRoleError(role)
        return True

    return check(predicate)


def bot_has_any_role(*roles: int | str) -> CheckDecorator:
    """Refuse when the bot has none of `roles` (IDs or names), with `BotMissingAnyRoleError`."""

    def predicate(ctx: "Context") -> bool:
        member = _member(ctx.me)
        if not any(member.has_role(role) for role in roles):
            raise BotMissingAnyRoleError(roles)
        return True

    return check(predicate)


def is_owner() -> CheckDecorator:
    """Allow only the bot's owner (or its team), with `NotOwnerError` for anyone else."""

    async def predicate(ctx: "Context") -> bool:
        if not await ctx.bot.is_owner(ctx.author):
            raise NotOwnerError
        return True

    return check(predicate)


def guild_only() -> CheckDecorator:
    """Refuse the command in DMs, with `NoPrivateMessageError`."""

    def predicate(ctx: "Context") -> bool:
        if ctx.guild is None:
            raise NoPrivateMessageError
        return True

    return check(predicate)


def dm_only() -> CheckDecorator:
    """Refuse the command in guilds, with `PrivateMessageOnlyError`."""

    def predicate(ctx: "Context") -> bool:
        if ctx.guild is not None:
            raise PrivateMessageOnlyError
        return True

    return check(predicate)


def is_nsfw() -> CheckDecorator:
    """Allow the command only in age-restricted channels (and DMs), with `NSFWChannelRequiredError`."""

    def predicate(ctx: "Context") -> bool:
        channel = ctx.channel
        if isinstance(channel, Thread):
            parent = channel.parent
            restricted = parent is not None and parent.is_nsfw()
        else:
            restricted = channel.is_nsfw() if isinstance(channel, GuildChannel) else True
        if not restricted:
            raise NSFWChannelRequiredError
        return True

    return check(predicate)


def cooldown[T: Decoratable](
    rate: int,
    per: float,
    type: BucketType = BucketType.DEFAULT,  # noqa: A002 - the bucket type, as every bot writes it
    *,
    clock: Clock | None = None,
) -> Callable[[T], T]:
    """Allow `rate` uses per `per` seconds per `type` bucket; refuse with `CommandOnCooldownError`.

    `clock` measures the window (tests pass a fake one).

    Raises:
        ValueError: `rate` is below 1 or `per` is not positive.
    """
    limiter = Cooldown["Context"](rate, per, key=type.key, clock=clock)

    def decorator(target: T) -> T:
        def on_command(command: Command) -> None:
            command.cooldown = limiter

        def on_function(pending: PendingSettings) -> None:
            pending.cooldown = limiter

        return _apply(target, on_command, on_function)

    return decorator


def dynamic_cooldown[T: Decoratable](
    cooldown: Callable[["Context"], Cooldown["Context"] | None],
    type: BucketType = BucketType.DEFAULT,  # noqa: A002 - the bucket type, as every bot writes it
    *,
    clock: Clock | None = None,
) -> Callable[[T], T]:
    """A cooldown whose limit `cooldown` chooses for each `type` bucket; `None` means no limit.

    `cooldown` gets the context of the bucket's first use and returns a `Cooldown(rate, per)`; it is
    asked again once the bucket's uses have expired. Refused uses raise `CommandOnCooldownError`.
    """
    limiter = DynamicCooldown["Context"](cooldown, key=type.key, clock=clock)

    def decorator(target: T) -> T:
        def on_command(command: Command) -> None:
            command.cooldown = limiter

        def on_function(pending: PendingSettings) -> None:
            pending.cooldown = limiter

        return _apply(target, on_command, on_function)

    return decorator


def max_concurrency[T: Decoratable](
    number: int, per: BucketType = BucketType.DEFAULT, *, wait: bool = False
) -> Callable[[T], T]:
    """Let at most `number` uses run at once per `per` bucket; refuse (or with `wait`, queue) the rest.

    Raises:
        ValueError: `number` is below 1.
    """
    if number < 1:
        msg = f"max_concurrency needs at least 1, not {number}"
        raise ValueError(msg)
    limit = MaxConcurrency(number, per, wait=wait)

    def decorator(target: T) -> T:
        def on_command(command: Command) -> None:
            command.max_concurrency = limit

        def on_function(pending: PendingSettings) -> None:
            pending.max_concurrency = limit

        return _apply(target, on_command, on_function)

    return decorator


def before_invoke[T: Decoratable](hook: Hook) -> Callable[[T], T]:
    """Run `hook` just before the command's callback, after its checks and parsing."""

    def decorator(target: T) -> T:
        def on_command(command: Command) -> None:
            command.before_invoke(hook)

        def on_function(pending: PendingSettings) -> None:
            pending.before_invoke = hook

        return _apply(target, on_command, on_function)

    return decorator


def after_invoke[T: Decoratable](hook: Hook) -> Callable[[T], T]:
    """Run `hook` after the command's callback, even when it raised."""

    def decorator(target: T) -> T:
        def on_command(command: Command) -> None:
            command.after_invoke(hook)

        def on_function(pending: PendingSettings) -> None:
            pending.after_invoke = hook

        return _apply(target, on_command, on_function)

    return decorator
