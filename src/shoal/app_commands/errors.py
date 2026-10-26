"""Errors raised while running application commands; `CommandTree.on_error` receives them.

Discord: https://docs.discord.com/developers/interactions/application-commands
"""

from collections.abc import Sequence

from shoal.client.client import ClientError
from shoal.core.errors import ShoalError
from shoal.rest.errors import BadRequestError


class AppCommandError(ShoalError):
    """Something went wrong running a command; the base of every error here."""


class CommandInvokeError(AppCommandError):
    """The command's callback raised `original`."""

    def __init__(self, command_name: str, original: Exception) -> None:
        """An error raised by command `command_name`."""
        super().__init__(f"command {command_name!r} raised {type(original).__name__}: {original}")
        self.command_name: str = command_name
        self.original: Exception = original


class TransformerError(AppCommandError):
    """An option's value could not become what the parameter asks for."""

    def __init__(self, parameter: str, value: object, reason: str) -> None:
        """`value` of option `parameter` could not be converted, because `reason`."""
        super().__init__(f"option {parameter!r}: cannot use {value!r}: {reason}")
        self.parameter: str = parameter
        self.value: object = value


class CommandNotFoundError(AppCommandError):
    """Discord sent a command this tree does not have (an old command still registered)."""

    def __init__(self, name: str) -> None:
        """Command `name` is unknown."""
        super().__init__(f"no command named {name!r}; sync the tree to remove it from Discord")
        self.name: str = name


class CheckFailureError(AppCommandError):
    """A check refused the interaction."""


class NoPrivateMessageError(CheckFailureError):
    """A guild-only command was used outside a guild."""

    def __init__(self) -> None:
        """The error for a guild-only command used in DMs."""
        super().__init__("this command can only be used in a server")


class MissingPermissionsError(CheckFailureError):
    """The user lacks permissions the command needs."""

    def __init__(self, missing: Sequence[str]) -> None:
        """The user lacks the permissions named in `missing`."""
        super().__init__(f"you are missing permissions: {', '.join(missing)}")
        self.missing_permissions: list[str] = list(missing)


class BotMissingPermissionsError(CheckFailureError):
    """The bot lacks permissions the command needs."""

    def __init__(self, missing: Sequence[str]) -> None:
        """The bot lacks the permissions named in `missing`."""
        super().__init__(f"the bot is missing permissions: {', '.join(missing)}")
        self.missing_permissions: list[str] = list(missing)


class MissingRoleError(CheckFailureError):
    """The user lacks the role the command needs."""

    def __init__(self, role: int | str) -> None:
        """The user lacks `role` (an ID or a name)."""
        super().__init__(f"you need the role {role!r}")
        self.missing_role: int | str = role


class MissingAnyRoleError(CheckFailureError):
    """The user has none of the roles the command accepts."""

    def __init__(self, roles: Sequence[int | str]) -> None:
        """The user has none of `roles`."""
        super().__init__(f"you need one of the roles {list(roles)!r}")
        self.missing_roles: list[int | str] = list(roles)


class CommandOnCooldownError(CheckFailureError):
    """The command was used again too soon."""

    def __init__(self, retry_after: float) -> None:
        """The command can be used again in `retry_after` seconds."""
        super().__init__(f"you are on cooldown; try again in {retry_after:.1f}s")
        self.retry_after: float = retry_after


class CommandAlreadyRegisteredError(AppCommandError, ValueError):
    """A command of that name and type is already in the tree (pass `override=True` to replace it)."""

    def __init__(self, name: str, guild_id: int | None) -> None:
        """Command `name` is taken globally (`guild_id` `None`) or in that guild."""
        where = "globally" if guild_id is None else f"in guild {guild_id}"
        super().__init__(f"a command named {name!r} is already registered {where}")
        self.name: str = name
        self.guild_id: int | None = guild_id


class CommandLimitReachedError(AppCommandError, ValueError):
    """The tree holds as many commands of that type as Discord allows."""

    def __init__(self, kind: str, limit: int, guild_id: int | None) -> None:
        """`limit` commands of `kind` are already registered globally or in that guild."""
        where = "globally" if guild_id is None else f"in guild {guild_id}"
        super().__init__(f"{limit} {kind} commands {where} is the most Discord allows")
        self.kind: str = kind
        self.limit: int = limit
        self.guild_id: int | None = guild_id


class CommandSignatureMismatchError(AppCommandError):
    """Discord sent a command whose options no longer match the code: sync the tree again."""

    def __init__(self, command_name: str) -> None:
        """Command `command_name` as Discord knows it differs from its code."""
        super().__init__(f"command {command_name!r} is out of date in Discord; sync the tree")
        self.command_name: str = command_name


class MissingApplicationIDError(AppCommandError, ClientError):
    """The tree needs the application's ID, known once the client has logged in."""

    def __init__(self) -> None:
        """The client has not logged in yet."""
        super().__init__("log in before syncing commands: the application ID is not known yet")


class CommandSyncFailureError(AppCommandError, BadRequestError):
    """Discord refused the commands a sync sent; `commands` names those its errors point at."""

    def __init__(self, original: BadRequestError, names: Sequence[str]) -> None:
        """Discord answered `original` to commands `names`, in the order they were sent."""
        BadRequestError.__init__(
            self, original.route, original.status, original.message, original.code, original.field_errors
        )
        refused = {error.path.split(".", 1)[0] for error in original.field_errors}
        self.commands: list[str] = [name for index, name in enumerate(names) if str(index) in refused]
