import inspect

from shoal.commands.errors import (
    BadBoolArgumentError,
    BadLiteralArgumentError,
    BadUnionArgumentError,
    BotMissingPermissionsError,
    BotMissingRoleError,
    ChannelNotReadableError,
    CheckAnyFailureError,
    CheckFailureError,
    CommandInvokeError,
    CommandNotFoundError,
    CommandOnCooldownError,
    ConversionError,
    DisabledCommandError,
    ExpectedClosingQuoteError,
    ExtensionAlreadyLoadedError,
    ExtensionFailedError,
    ExtensionNotFoundError,
    ExtensionNotLoadedError,
    HybridCommandError,
    InvalidEndOfQuotedStringError,
    MaxConcurrencyReachedError,
    MemberNotFoundError,
    MissingAnyRoleError,
    MissingPermissionsError,
    MissingRequiredArgumentError,
    MissingRoleError,
    NoEntryPointError,
    NoPrivateMessageError,
    NotOwnerError,
    NSFWChannelRequiredError,
    PrivateMessageOnlyError,
    RangeError,
    TooManyArgumentsError,
    UnexpectedQuoteError,
)
from shoal.commands.parameters import parameter_of


def test_errors_say_what_went_wrong() -> None:
    member = parameter_of(inspect.Parameter("member", inspect.Parameter.POSITIONAL_OR_KEYWORD), str)
    original = ValueError("bad")
    messages = {
        CommandNotFoundError("ping"): "no command named 'ping'",
        DisabledCommandError("ping"): "the command 'ping' is disabled",
        CommandInvokeError("ping", original): "command 'ping' raised ValueError: bad",
        HybridCommandError(original): "bad",
        MissingRequiredArgumentError(member): "member is a required argument that is missing",
        TooManyArgumentsError("extra"): "too many arguments: 'extra' was not expected",
        UnexpectedQuoteError('"'): "unexpected quote mark '\"' in a non-quoted argument",
        InvalidEndOfQuotedStringError("x"): "expected a space after a closing quote, got 'x'",
        ExpectedClosingQuoteError('"'): 'expected a closing "',
        BadBoolArgumentError("maybe"): "'maybe' is not a recognised yes or no",
        BadLiteralArgumentError("size", ["s", "m"], "xl"): "size must be one of 's', 'm', not 'xl'",
        BadUnionArgumentError(
            "value", [BadBoolArgumentError("x")]
        ): "could not convert 'value': 'x' is not a recognised yes or no",
        MemberNotFoundError("carol"): "member 'carol' not found",
        ChannelNotReadableError("#secret"): "cannot read messages in #secret",
        RangeError(9, 1, None): "9 is outside the range 1 to inf",
        RangeError(0, None, 5): "0 is outside the range -inf to 5",
        ConversionError(int, original): "<class 'int'> raised ValueError: bad",
        CheckFailureError("no"): "no",
        CheckAnyFailureError(
            [CheckFailureError("a")]
        ): "you do not meet any of the requirements to use this command",
        NoPrivateMessageError(): "this command cannot be used in private messages",
        PrivateMessageOnlyError(): "this command can only be used in private messages",
        NotOwnerError(): "you do not own this bot",
        MissingPermissionsError(["ban_members"]): "you are missing permissions: ban_members",
        BotMissingPermissionsError(["embed_links"]): "the bot is missing permissions: embed_links",
        MissingRoleError("mods"): "you need the role 'mods'",
        BotMissingRoleError(5): "the bot needs the role 5",
        MissingAnyRoleError([1, "mods"]): "you need one of the roles [1, 'mods']",
        NSFWChannelRequiredError(): "this command can only be used in age-restricted channels",
        CommandOnCooldownError(2.25): "you are on cooldown; try again in 2.2s",
        MaxConcurrencyReachedError(1): "this command can only be used 1 times at once",
        ExtensionAlreadyLoadedError("ext"): "extension 'ext' is already loaded",
        ExtensionNotLoadedError("ext"): "extension 'ext' has not been loaded",
        ExtensionNotFoundError("ext"): "extension 'ext' could not be found",
        NoEntryPointError("ext"): "extension 'ext' has no 'setup' function",
        ExtensionFailedError("ext", original): "extension 'ext' raised ValueError: bad",
    }
    for error, message in messages.items():
        assert str(error) == message, type(error).__name__
