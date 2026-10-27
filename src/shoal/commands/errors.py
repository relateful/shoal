"""Errors raised while finding, parsing, checking and running prefix and hybrid commands.

`Bot.on_command_error` receives them. The names are those every bot developer knows, with the
`Error` ending every Shoal exception has: `MissingRequiredArgument` is `MissingRequiredArgumentError`.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from shoal.core.errors import ShoalError

if TYPE_CHECKING:
    from shoal.commands.flags import Flag
    from shoal.commands.parameters import Parameter


class CommandError(ShoalError):
    """Something went wrong with a command; the base of every error here."""


class CommandNotFoundError(CommandError):
    """A message started with the prefix but named no command."""

    def __init__(self, name: str) -> None:
        """No command is called `name`."""
        super().__init__(f"no command named {name!r}")
        self.name: str = name


class DisabledCommandError(CommandError):
    """The command is disabled."""

    def __init__(self, name: str) -> None:
        """Command `name` is disabled."""
        super().__init__(f"the command {name!r} is disabled")
        self.name: str = name


class CommandInvokeError(CommandError):
    """The command's callback raised `original`."""

    def __init__(self, name: str, original: Exception) -> None:
        """Command `name` raised `original`."""
        super().__init__(f"command {name!r} raised {type(original).__name__}: {original}")
        self.name: str = name
        self.original: Exception = original


class HybridCommandError(CommandError):
    """A hybrid command used as a slash command failed in the slash-command machinery."""

    def __init__(self, original: Exception) -> None:
        """The slash side raised `original`."""
        super().__init__(str(original))
        self.original: Exception = original


class UserInputError(CommandError):
    """The arguments given cannot run the command."""


class MissingRequiredArgumentError(UserInputError):
    """A required argument was left out."""

    def __init__(self, parameter: "Parameter") -> None:
        """`parameter` was not given."""
        super().__init__(f"{parameter.name} is a required argument that is missing")
        self.parameter: Parameter = parameter


class MissingRequiredAttachmentError(UserInputError):
    """A parameter that takes an attached file had none left to take."""

    def __init__(self, parameter: "Parameter") -> None:
        """`parameter` got no attachment."""
        super().__init__(f"{parameter.name} is a required attachment that is missing")
        self.parameter: Parameter = parameter


class TooManyArgumentsError(UserInputError):
    """More arguments were given than the command takes (and it does not ignore extras)."""

    def __init__(self, extra: str) -> None:
        """`extra` was left over."""
        super().__init__(f"too many arguments: {extra!r} was not expected")
        self.extra: str = extra


class ArgumentParsingError(UserInputError):
    """The arguments could not be split into words: a quote is wrong."""


class UnexpectedQuoteError(ArgumentParsingError):
    """A quote appeared inside a word that did not start with one."""

    def __init__(self, quote: str) -> None:
        """`quote` was unexpected."""
        super().__init__(f"unexpected quote mark {quote!r} in a non-quoted argument")
        self.quote: str = quote


class InvalidEndOfQuotedStringError(ArgumentParsingError):
    """A closing quote was followed by something other than a space."""

    def __init__(self, character: str) -> None:
        """`character` followed a closing quote."""
        super().__init__(f"expected a space after a closing quote, got {character!r}")
        self.character: str = character


class ExpectedClosingQuoteError(ArgumentParsingError):
    """A quoted argument was never closed."""

    def __init__(self, quote: str) -> None:
        """`quote` was never closed."""
        super().__init__(f"expected a closing {quote}")
        self.quote: str = quote


class BadArgumentError(UserInputError):
    """An argument could not be converted to what the parameter asks for."""


class BadBoolArgumentError(BadArgumentError):
    """An argument is not a yes or no."""

    def __init__(self, argument: str) -> None:
        """`argument` is not a boolean."""
        super().__init__(f"{argument!r} is not a recognised yes or no")
        self.argument: str = argument


class BadLiteralArgumentError(BadArgumentError):
    """An argument is none of the values the parameter allows."""

    def __init__(self, name: str, literals: Sequence[object], argument: str) -> None:
        """`argument` of parameter `name` is none of `literals`."""
        allowed = ", ".join(repr(value) for value in literals)
        super().__init__(f"{name} must be one of {allowed}, not {argument!r}")
        self.name: str = name
        self.literals: list[object] = list(literals)
        self.argument: str = argument


class BadUnionArgumentError(BadArgumentError):
    """An argument matched none of the types the parameter allows."""

    def __init__(self, name: str, errors: Sequence[CommandError]) -> None:
        """Every conversion of parameter `name` failed, with `errors`."""
        super().__init__(f"could not convert {name!r}: " + "; ".join(str(error) for error in errors))
        self.name: str = name
        self.errors: list[CommandError] = list(errors)


class _NotFoundError(BadArgumentError):
    """Something an argument names could not be found."""

    kind: str = "object"

    def __init__(self, argument: str) -> None:
        """No such thing as `argument`."""
        super().__init__(f"{self.kind} {argument!r} not found")
        self.argument: str = argument


class MemberNotFoundError(_NotFoundError):
    """No member matches the argument."""

    kind = "member"


class UserNotFoundError(_NotFoundError):
    """No user matches the argument."""

    kind = "user"


class RoleNotFoundError(_NotFoundError):
    """No role matches the argument."""

    kind = "role"


class ChannelNotFoundError(_NotFoundError):
    """No channel matches the argument."""

    kind = "channel"


class ThreadNotFoundError(_NotFoundError):
    """No thread matches the argument."""

    kind = "thread"


class MessageNotFoundError(_NotFoundError):
    """No message matches the argument."""

    kind = "message"


class EmojiNotFoundError(_NotFoundError):
    """No emoji matches the argument."""

    kind = "emoji"


class GuildNotFoundError(_NotFoundError):
    """No guild matches the argument."""

    kind = "guild"


class GuildStickerNotFoundError(_NotFoundError):
    """No sticker of the guild matches the argument."""

    kind = "sticker"


class ScheduledEventNotFoundError(_NotFoundError):
    """No scheduled event of the guild matches the argument."""

    kind = "scheduled event"


class SoundboardSoundNotFoundError(_NotFoundError):
    """No soundboard sound of the guild matches the argument."""

    kind = "soundboard sound"


class ObjectNotFoundError(_NotFoundError):
    """The argument is not an ID or a mention."""

    kind = "ID or mention"


class PartialEmojiConversionFailureError(_NotFoundError):
    """The argument is not a custom emoji's text (`<:name:id>`)."""

    kind = "custom emoji"


class BadColourArgumentError(BadArgumentError):
    """The argument is not a colour: `#RRGGBB`, `0xRRGGBB`, `RRGGBB` or `rgb(r, g, b)`."""

    def __init__(self, argument: str) -> None:
        """`argument` is not a colour."""
        super().__init__(f"{argument!r} is not a colour")
        self.argument: str = argument


BadColorArgumentError = BadColourArgumentError
"""The same as `BadColourArgumentError`."""


class BadInviteArgumentError(BadArgumentError):
    """The argument is not an invite, or the invite has expired."""

    def __init__(self, argument: str) -> None:
        """`argument` is not a valid invite."""
        super().__init__(f"{argument!r} is not a valid invite")
        self.argument: str = argument


class BadTimestampArgumentError(BadArgumentError):
    """The argument is not a timestamp (`<t:1618953630>`)."""

    def __init__(self, argument: str) -> None:
        """`argument` is not a timestamp."""
        super().__init__(f"{argument!r} is not a timestamp")
        self.argument: str = argument


class FlagError(BadArgumentError):
    """A flag could not be read."""


class BadFlagArgumentError(FlagError):
    """A flag's value did not convert."""

    def __init__(self, flag: "Flag", argument: str, original: CommandError) -> None:
        """`argument`, given to `flag`, did not convert (`original`)."""
        super().__init__(f"could not convert {argument!r} for flag {flag.name!r}: {original}")
        self.flag: Flag = flag
        self.argument: str = argument
        self.original: CommandError = original


class MissingFlagArgumentError(FlagError):
    """A flag was given without a value (or a tuple flag with too few words)."""

    def __init__(self, flag: "Flag") -> None:
        """`flag` was given empty."""
        super().__init__(f"flag {flag.name!r} needs a value")
        self.flag: Flag = flag


class MissingRequiredFlagError(FlagError):
    """A flag without a default was left out."""

    def __init__(self, flag: "Flag") -> None:
        """`flag` was not given."""
        super().__init__(f"flag {flag.name!r} is required and missing")
        self.flag: Flag = flag


class TooManyFlagsError(FlagError):
    """A flag was given more times than it takes."""

    def __init__(self, flag: "Flag", values: Sequence[str]) -> None:
        """`flag` was given `values`, more than its `max_args`."""
        super().__init__(f"flag {flag.name!r} takes at most {flag.max_args} values, not {len(values)}")
        self.flag: Flag = flag
        self.values: list[str] = list(values)


class ChannelNotReadableError(BadArgumentError):
    """The bot cannot read the channel the argument names."""

    def __init__(self, argument: str) -> None:
        """The bot cannot read channel `argument`."""
        super().__init__(f"cannot read messages in {argument}")
        self.argument: str = argument


class RangeError(BadArgumentError):
    """A number or a length is outside the parameter's range."""

    def __init__(self, value: object, minimum: float | None, maximum: float | None) -> None:
        """`value` is outside `minimum` to `maximum`."""
        bounds = f"{'-inf' if minimum is None else minimum} to {'inf' if maximum is None else maximum}"
        super().__init__(f"{value!r} is outside the range {bounds}")
        self.value: object = value
        self.minimum: float | None = minimum
        self.maximum: float | None = maximum


class ConversionError(CommandError):
    """A converter raised something other than a command error."""

    def __init__(self, converter: object, original: Exception) -> None:
        """`converter` raised `original`."""
        super().__init__(f"{converter!r} raised {type(original).__name__}: {original}")
        self.converter: object = converter
        self.original: Exception = original


class CheckFailureError(CommandError):
    """A check refused the command."""


class CheckAnyFailureError(CheckFailureError):
    """Every check given to `check_any` refused."""

    def __init__(self, errors: Sequence[CheckFailureError]) -> None:
        """Each check failed with one of `errors`."""
        super().__init__("you do not meet any of the requirements to use this command")
        self.errors: list[CheckFailureError] = list(errors)


class NoPrivateMessageError(CheckFailureError):
    """A server-only command was used in DMs."""

    def __init__(self) -> None:
        """The error for a server-only command used in DMs."""
        super().__init__("this command cannot be used in private messages")


class PrivateMessageOnlyError(CheckFailureError):
    """A DM-only command was used in a server."""

    def __init__(self) -> None:
        """The error for a DM-only command used in a server."""
        super().__init__("this command can only be used in private messages")


class NotOwnerError(CheckFailureError):
    """Only the bot's owner may use the command."""

    def __init__(self) -> None:
        """The error for someone other than the owner."""
        super().__init__("you do not own this bot")


class MissingPermissionsError(CheckFailureError):
    """The author lacks permissions the command needs."""

    def __init__(self, missing: Sequence[str]) -> None:
        """The author lacks the permissions named in `missing`."""
        super().__init__(f"you are missing permissions: {', '.join(missing)}")
        self.missing_permissions: list[str] = list(missing)


class BotMissingPermissionsError(CheckFailureError):
    """The bot lacks permissions the command needs."""

    def __init__(self, missing: Sequence[str]) -> None:
        """The bot lacks the permissions named in `missing`."""
        super().__init__(f"the bot is missing permissions: {', '.join(missing)}")
        self.missing_permissions: list[str] = list(missing)


class MissingRoleError(CheckFailureError):
    """The author lacks the role the command needs."""

    def __init__(self, role: int | str) -> None:
        """The author lacks `role` (an ID or a name)."""
        super().__init__(f"you need the role {role!r}")
        self.missing_role: int | str = role


class BotMissingRoleError(CheckFailureError):
    """The bot lacks the role the command needs."""

    def __init__(self, role: int | str) -> None:
        """The bot lacks `role` (an ID or a name)."""
        super().__init__(f"the bot needs the role {role!r}")
        self.missing_role: int | str = role


class MissingAnyRoleError(CheckFailureError):
    """The author has none of the roles the command accepts."""

    def __init__(self, roles: Sequence[int | str]) -> None:
        """The author has none of `roles`."""
        super().__init__(f"you need one of the roles {list(roles)!r}")
        self.missing_roles: list[int | str] = list(roles)


class BotMissingAnyRoleError(CheckFailureError):
    """The bot has none of the roles the command accepts."""

    def __init__(self, roles: Sequence[int | str]) -> None:
        """The bot has none of `roles`."""
        super().__init__(f"the bot needs one of the roles {list(roles)!r}")
        self.missing_roles: list[int | str] = list(roles)


class NSFWChannelRequiredError(CheckFailureError):
    """The command can only be used in age-restricted channels."""

    def __init__(self) -> None:
        """The error for an age-restricted command used elsewhere."""
        super().__init__("this command can only be used in age-restricted channels")


class CommandOnCooldownError(CommandError):
    """The command was used again too soon."""

    def __init__(self, retry_after: float) -> None:
        """The command can be used again in `retry_after` seconds."""
        super().__init__(f"you are on cooldown; try again in {retry_after:.1f}s")
        self.retry_after: float = retry_after


class MaxConcurrencyReachedError(CommandError):
    """As many uses of the command as allowed are already running."""

    def __init__(self, number: int) -> None:
        """At most `number` uses may run at once."""
        super().__init__(f"this command can only be used {number} times at once")
        self.number: int = number


class ExtensionError(ShoalError):
    """An extension could not be loaded, unloaded or reloaded."""

    def __init__(self, message: str, *, name: str) -> None:
        """An error about extension `name`."""
        super().__init__(message)
        self.name: str = name


class ExtensionAlreadyLoadedError(ExtensionError):
    """The extension is already loaded."""

    def __init__(self, name: str) -> None:
        """Extension `name` is already loaded."""
        super().__init__(f"extension {name!r} is already loaded", name=name)


class ExtensionNotLoadedError(ExtensionError):
    """The extension is not loaded."""

    def __init__(self, name: str) -> None:
        """Extension `name` is not loaded."""
        super().__init__(f"extension {name!r} has not been loaded", name=name)


class ExtensionNotFoundError(ExtensionError):
    """No module has the extension's name."""

    def __init__(self, name: str) -> None:
        """No module is called `name`."""
        super().__init__(f"extension {name!r} could not be found", name=name)


class NoEntryPointError(ExtensionError):
    """The extension's module has no `setup` function."""

    def __init__(self, name: str) -> None:
        """Extension `name` has no `setup`."""
        super().__init__(f"extension {name!r} has no 'setup' function", name=name)


class ExtensionFailedError(ExtensionError):
    """The extension's module or its `setup` raised."""

    def __init__(self, name: str, original: Exception) -> None:
        """Loading extension `name` raised `original`."""
        super().__init__(f"extension {name!r} raised {type(original).__name__}: {original}", name=name)
        self.original: Exception = original
