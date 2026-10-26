from shoal.app_commands.errors import (
    BotMissingPermissionsError,
    CommandInvokeError,
    CommandNotFoundError,
    CommandOnCooldownError,
    MissingAnyRoleError,
    MissingPermissionsError,
    MissingRoleError,
    NoPrivateMessageError,
    TransformerError,
)


def test_errors_say_what_went_wrong() -> None:
    original = ValueError("bad value")
    invoked = CommandInvokeError("tags show", original)
    assert str(invoked) == "command 'tags show' raised ValueError: bad value"
    assert invoked.original is original
    assert str(TransformerError("days", "x", "not a number")) == "option 'days': cannot use 'x': not a number"
    assert "sync the tree" in str(CommandNotFoundError("gone"))
    assert str(NoPrivateMessageError()) == "this command can only be used in a server"
    assert str(MissingPermissionsError(["ban_members"])) == "you are missing permissions: ban_members"
    assert str(BotMissingPermissionsError(["embed_links"])) == "the bot is missing permissions: embed_links"
    assert str(MissingRoleError("mods")) == "you need the role 'mods'"
    assert str(MissingAnyRoleError([1, "mods"])) == "you need one of the roles [1, 'mods']"
    assert str(CommandOnCooldownError(2.25)) == "you are on cooldown; try again in 2.2s"
